"""
RQ worker function for batch image processing.
Run the worker separately:
    rq worker --url redis://localhost:6379/0
"""
import io
import uuid
import logging
from pathlib import Path

from sqlalchemy import select, text

from app.db import SyncSessionLocal
from app.models import Image, Job
from app.services.hashing import compute_sha256, compute_phash
from app.services.duplicate_check import resolve_canonical_id
from app.services.storage import save_file, StorageLimitExceeded


logger = logging.getLogger(__name__)


def _resolve_canonical_sync(session, matched_image):
    """Sync version of resolve_canonical_id — walks the chain without async."""
    current = matched_image
    hops = 0
    while current.canonical_id is not None:
        if hops >= 20:
            raise RuntimeError(
                f"resolve_canonical_id: chain exceeded 20 hops from {matched_image.id}"
            )
        parent = session.get(Image, current.canonical_id)
        if parent is None:
            logger.warning(
                "resolve_canonical_id: dangling FK %s from row %s — stopping here",
                current.canonical_id, current.id,
            )
            break
        current = parent
        hops += 1
    return current.id


def _load_bktree_sync(session):
    """Load BK-tree from DB synchronously."""
    import pybktree
    import imagehash

    def hamming_distance(a, b):
        return bin(int(a, 16) ^ int(b, 16)).count("1")

    tree = pybktree.BKTree(hamming_distance)
    result = session.execute(text("SELECT phash FROM images"))
    for row in result.all():
        tree.add(row[0])
    return tree


def _load_faiss_sync(session):
    """Load FAISS index from DB synchronously."""
    import faiss
    import numpy as np

    class _Wrapper:
        def __init__(self):
            self.index = faiss.IndexIDMap(faiss.IndexFlatIP(512))
            self.id_map = {}
            self.current_id = 1

        def add(self, embedding_list, image_id):
            arr = np.array([embedding_list], dtype=np.float32)
            faiss.normalize_L2(arr)
            self.index.add_with_ids(arr, np.array([self.current_id], dtype=np.int64))
            self.id_map[self.current_id] = image_id
            self.current_id += 1

        def search(self, embedding_list, top_k=5):
            if self.index.ntotal == 0:
                return []
            arr = np.array([embedding_list], dtype=np.float32)
            faiss.normalize_L2(arr)
            scores, indices = self.index.search(arr, top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx != -1 and idx in self.id_map:
                    results.append({"id": self.id_map[idx], "similarity": float(score)})
            return results

    wrapper = _Wrapper()
    result = session.execute(
        text("SELECT id, embedding FROM images WHERE embedding IS NOT NULL")
    )
    for row in result.all():
        wrapper.add(row[1], str(row[0]))
    return wrapper


def process_image_job(job_id: str, file_path: str, filename: str) -> None:
    """
    Process a single image as an RQ background task.
    Same pipeline as POST /images/check — sha256 → phash → CLIP/FAISS → insert.
    Updates the parent Job row on completion or failure.
    """
    from PIL import Image as PILImage
    from app.services.embedding import compute_embedding

    with SyncSessionLocal() as session:
        try:
            file_bytes = Path(file_path).read_bytes()
            sha256 = compute_sha256(file_bytes)
            phash = compute_phash(file_bytes)
            img = PILImage.open(io.BytesIO(file_bytes))
            embedding = compute_embedding(img)

            # Load indexes fresh from DB for this job
            bktree = _load_bktree_sync(session)
            faiss_wrapper = _load_faiss_sync(session)

            # --- Scoring ---
            status = "accepted"
            reason_code = "UNIQUE"
            canonical_id = None
            similarity = None
            hamming_distance = None

            # 1. Exact SHA-256
            existing = session.execute(
                select(Image).where(Image.sha256 == sha256).limit(1)
            ).scalars().first()
            if existing is not None:
                status = "rejected"
                reason_code = "EXACT_DUPLICATE"
                canonical_id = _resolve_canonical_sync(session, existing)

            # 2. pHash BK-tree
            if status == "accepted":
                near_dupes = bktree.find(phash, 8)
                if near_dupes:
                    best_dist, best_phash = near_dupes[0]
                    hamming_distance = best_dist
                    row = session.execute(
                        text("SELECT id FROM images WHERE phash = :phash LIMIT 1"),
                        {"phash": best_phash}
                    ).first()
                    match_img = session.get(Image, row[0]) if row else None
                    if best_dist <= 4:
                        status = "rejected"
                        reason_code = "NEAR_DUPLICATE_HASH"
                        canonical_id = _resolve_canonical_sync(session, match_img) if match_img else None
                    elif best_dist <= 8:
                        status = "needs_review"
                        reason_code = "NEAR_DUPLICATE_BORDERLINE"
                        canonical_id = _resolve_canonical_sync(session, match_img) if match_img else None

            # 3. CLIP / FAISS semantic
            if status == "accepted":
                faiss_results = faiss_wrapper.search(embedding, top_k=5)
                if faiss_results:
                    top = faiss_results[0]
                    similarity = top["similarity"]
                    sem_match_img = session.get(Image, uuid.UUID(top["id"]))
                    if similarity >= 0.92:
                        status = "rejected"
                        reason_code = "SEMANTIC_DUPLICATE"
                        canonical_id = _resolve_canonical_sync(session, sem_match_img) if sem_match_img else uuid.UUID(top["id"])
                    elif similarity >= 0.85:
                        status = "needs_review"
                        reason_code = "SEMANTIC_BORDERLINE"
                        canonical_id = _resolve_canonical_sync(session, sem_match_img) if sem_match_img else uuid.UUID(top["id"])

            # Extract file byte processing early since we don't save arbitrary files anymore
            # Only save if we want to store it in the cloud.
            try:
                storage_path_key = save_file(file_bytes, sha256, filename)
            except StorageLimitExceeded:
                # Capture standard storage exception mapped to job state
                raise Exception("Storage Limit Exceeded (500MB)")

            # Always insert
            new_image = Image(
                id=uuid.uuid4(),
                filename=filename,
                storage_path=storage_path_key,
                sha256=sha256,

                phash=phash,
                embedding=embedding,
                status=status,
                reason_code=reason_code,
                canonical_id=canonical_id,
            )
            session.add(new_image)

            # Increment Job.processed
            job = session.get(Job, uuid.UUID(job_id))
            if job:
                job.processed += 1
                if job.processed >= job.total:
                    job.status = "complete"

            session.commit()
            logger.info("process_image_job: %s → %s/%s", filename, status, reason_code)

        except Exception as exc:
            logger.exception("process_image_job: error on %s", filename)
            try:
                session.rollback()  # NEW: clear any failed transaction state first
                job = session.get(Job, uuid.UUID(job_id))
                if job:
                    prev = job.error_message or ""
                    job.error_message = f"{prev}[{filename}] {exc}\n"
                    job.processed += 1
                    if job.processed >= job.total:
                        job.status = "complete"
                    session.commit()
            except Exception:
                logger.exception("process_image_job: failed to update job error_message — job_id=%s filename=%s", job_id, filename)
