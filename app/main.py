import uuid
import os
import logging

logger = logging.getLogger(__name__)

import redis.asyncio as aioredis
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional, Literal
from rq import Queue
from redis import Redis
from sqlalchemy import text, select, func, desc, asc, or_
from pydantic import BaseModel

from app.config import settings
from app.db import engine, AsyncSessionLocal
from app.models import Image, Job
from app.services.hashing import compute_sha256, compute_phash
from app.services.duplicate_check import check_exact_duplicate, resolve_canonical_id
from app.services.bktree_index import load_bktree_from_db, find_near_duplicates, insert_into_bktree
from app.services.embedding import compute_embedding
from app.services.faiss_index import load_faiss_from_db
from app.worker import process_image_job
from app.services.storage import save_file, StorageLimitExceeded
import numpy as np


from fastapi.middleware.cors import CORSMiddleware

_redis_conn = Redis.from_url("redis://localhost:6379/0")
_rq_queue = Queue(connection=_redis_conn)

app = FastAPI(title="Argus")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Only import torch during startup/execution, to avoid slow initializations
    # loading FAISS and BKTree
    async with AsyncSessionLocal() as session:
        app.state.bktree = await load_bktree_from_db(session)
        app.state.faiss = await load_faiss_from_db(session)
        
    # Local disk storage — no bucket initialisation needed.



@app.get("/health")
async def health():
    # --- Postgres check ---
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        pg_status = "ok"
    except Exception as exc:
        pg_status = f"error: {exc}"

    # --- Redis check ---
    redis_status = "ok"

    return {"postgres": pg_status, "redis": redis_status}


@app.post("/images/check")
async def check_image(file: UploadFile = File(...)):
    import io
    from PIL import Image as PILImage

    file_bytes = await file.read()
    sha256 = compute_sha256(file_bytes)

    # Pre-compute all signals upfront (needed in every branch for the inserted row)
    phash = compute_phash(file_bytes)
    img = PILImage.open(io.BytesIO(file_bytes))
    embedding = compute_embedding(img)

    # --- Scoring logic (determines status/reason_code/canonical_id) ---
    status = "accepted"
    reason_code = "UNIQUE"
    canonical_id = None
    similarity = None
    hamming_distance = None

    async with AsyncSessionLocal() as session:
        # 1. Exact SHA-256 match
        existing = await check_exact_duplicate(session, sha256)
        if existing is not None:
            status = "rejected"
            reason_code = "EXACT_DUPLICATE"
            canonical_id = await resolve_canonical_id(session, existing)

        # 2. pHash BK-tree check (only if not already determined)
        if status == "accepted":
            near_dupes = find_near_duplicates(app.state.bktree, phash, max_distance=8)
            if near_dupes:
                # near_dupes is sorted by distance; take the closest
                best_dist, best_phash = near_dupes[0]
                hamming_distance = best_dist

                # Look up the canonical row for this phash
                stmt = text("SELECT id FROM images WHERE phash = :phash LIMIT 1")
                result = await session.execute(stmt, {"phash": best_phash})
                row = result.first()
                # Fetch the full Image object so we can walk its canonical chain
                match_img = await session.get(Image, row[0]) if row else None

                if best_dist <= 4:
                    status = "rejected"
                    reason_code = "NEAR_DUPLICATE_HASH"
                    canonical_id = await resolve_canonical_id(session, match_img) if match_img else None
                elif best_dist <= 8:
                    status = "needs_review"
                    reason_code = "NEAR_DUPLICATE_BORDERLINE"
                    canonical_id = await resolve_canonical_id(session, match_img) if match_img else None

        # 3. CLIP / FAISS semantic check (only if still undecided)
        if status == "accepted":
            faiss_results = app.state.faiss.search(embedding, top_k=5)
            if faiss_results:
                top = faiss_results[0]
                similarity = top["similarity"]
                if similarity >= 0.92:
                    status = "rejected"
                    reason_code = "SEMANTIC_DUPLICATE"
                    sem_match_img = await session.get(Image, uuid.UUID(top["id"]))
                    canonical_id = await resolve_canonical_id(session, sem_match_img) if sem_match_img else uuid.UUID(top["id"])
                elif similarity >= 0.85:
                    status = "needs_review"
                    reason_code = "SEMANTIC_BORDERLINE"
                    sem_match_img = await session.get(Image, uuid.UUID(top["id"]))
                    canonical_id = await resolve_canonical_id(session, sem_match_img) if sem_match_img else uuid.UUID(top["id"])

        # 4. Always insert — every upload gets a permanent record
        new_image = Image(
            id=uuid.uuid4(),
            filename=file.filename or "unknown",
            storage_path="unset",
            sha256=sha256,
            phash=phash,
            embedding=embedding,
            status=status,
            reason_code=reason_code,
            canonical_id=canonical_id,
        )
        
        try:
            storage_path_key = save_file(file_bytes, sha256, file.filename or "unknown")
            new_image.storage_path = storage_path_key
        except StorageLimitExceeded:
            raise HTTPException(status_code=400, detail={"status": "error", "reason": "storage_limit_exceeded"})

        session.add(new_image)
        await session.commit()
        await session.refresh(new_image)

        # 5. Always index — rejected images are still useful for future lookups
        insert_into_bktree(app.state.bktree, phash)
        app.state.faiss.add(embedding, str(new_image.id))

        return {
            "id": str(new_image.id),
            "status": status,
            "reason_code": reason_code,
            "canonical_id": str(canonical_id) if canonical_id else None,
            "storage_path": storage_path_key,
            "sha256": sha256,
            "phash": phash,
            "hamming_distance": hamming_distance,
            "similarity": similarity
        }

@app.get("/images")
async def list_images(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "newest"
):
    page_size = min(max(1, page_size), 100)
    page = max(1, page)
    offset = (page - 1) * page_size

    async with AsyncSessionLocal() as session:
        query = select(Image)
        count_query = select(func.count()).select_from(Image)

        if status:
            query = query.where(Image.status == status)
            count_query = count_query.where(Image.status == status)

        if sort == "oldest":
            query = query.order_by(asc(Image.created_at))
        else:
            query = query.order_by(desc(Image.created_at))

        query = query.offset(offset).limit(page_size)

        total_items = (await session.execute(count_query)).scalar() or 0
        result = await session.execute(query)
        images = result.scalars().all()

        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1

        items = []
        for img in images:
            items.append({
                "id": str(img.id),
                "filename": img.filename,
                "status": img.status,
                "reason_code": img.reason_code,
                "canonical_id": str(img.canonical_id) if img.canonical_id else None,
                "sha256": img.sha256,
                "phash": img.phash,
                "created_at": img.created_at.isoformat() if img.created_at else None,
                "storage_path": img.storage_path,
                "reviewed_by_human": img.reviewed_by_human,
                "reviewed_at": img.reviewed_at.isoformat() if img.reviewed_at else None
            })

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages
    }

@app.get("/images/{image_id}/file")
async def get_image_file(image_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        image = await session.get(Image, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        path = image.storage_path
        if not path or path == "unset" or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Image file unavailable on disk")
            
        return FileResponse(path)


class ReviewRequest(BaseModel):
    decision: Literal["accepted", "rejected"]

@app.post("/images/{image_id}/review")
async def review_image(image_id: uuid.UUID, payload: ReviewRequest):
    async with AsyncSessionLocal() as session:
        image = await session.get(Image, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        image.status = payload.decision
        image.reviewed_by_human = True
        image.reviewed_at = func.now()
        image.reason_code = "MANUAL_REVIEW"
        
        session.add(image)
        await session.commit()
        await session.refresh(image)
        
        return {
            "id": str(image.id),
            "filename": image.filename,
            "status": image.status,
            "reason_code": image.reason_code,
            "canonical_id": str(image.canonical_id) if image.canonical_id else None,
            "sha256": image.sha256,
            "phash": image.phash,
            "created_at": image.created_at.isoformat() if image.created_at else None,
            "storage_path": image.storage_path,
            "reviewed_by_human": image.reviewed_by_human,
            "reviewed_at": image.reviewed_at.isoformat() if image.reviewed_at else None
        }


@app.post("/images/batch-check")
async def batch_check_images(files: List[UploadFile] = File(...)):
    """Enqueue multiple images for background processing via RQ."""
    job_id = uuid.uuid4()
    total = len(files)

    # Create Job row
    async with AsyncSessionLocal() as session:
        job = Job(id=job_id, status="queued", total=total, processed=0)
        session.add(job)
        await session.commit()

    # Save files to temp storage, enqueue one RQ task per file
    tmp_dir = os.path.join("tmp_uploads", str(job_id))
    os.makedirs(tmp_dir, exist_ok=True)

    for upload in files:
        file_bytes = await upload.read()
        safe_name = os.path.basename(upload.filename or "unknown")
        file_path = os.path.join(tmp_dir, safe_name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        _rq_queue.enqueue(
            process_image_job,
            str(job_id),
            file_path,
            safe_name,
            job_timeout=-1
        )

    return {"job_id": str(job_id), "total": total, "status": "queued"}


# ---------- helpers for import-url ----------
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ZIP_MAGIC = b"PK\x03\x04"


def _is_zip(content_type: str, first_bytes: bytes) -> bool:
    return first_bytes[:4] == _ZIP_MAGIC or "zip" in content_type.lower()


class _UrlImportRequest(BaseModel):
    url: str

@app.post("/images/import-url")
async def import_from_url(payload: _UrlImportRequest):
    """
    Download a single image or a .zip archive from a URL and enqueue
    each image through the existing duplicate-detection pipeline.
    """
    import zipfile
    import tempfile
    import httpx

    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail={"error": "url field is required"})

    max_bytes = settings.MAX_IMPORT_SIZE_MB * 1024 * 1024

    # ---- Download with size guard ----
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # HEAD first — respect Content-Length if present
            try:
                head = await client.head(url)
                cl = int(head.headers.get("content-length", 0))
                if cl > max_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "import_too_large",
                            "reason": f"Content-Length {cl} bytes exceeds limit of {settings.MAX_IMPORT_SIZE_MB} MB",
                        },
                    )
                content_type = head.headers.get("content-type", "")
            except httpx.HTTPError:
                # HEAD not supported by some servers — fall through
                content_type = ""

            # Stream the body, abort if it exceeds the cap
            chunks: list[bytes] = []
            downloaded = 0
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                # Update content-type from GET response (more reliable)
                content_type = resp.headers.get("content-type", content_type)
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "import_too_large",
                                "reason": f"Download exceeded {settings.MAX_IMPORT_SIZE_MB} MB limit",
                            },
                        )
                    chunks.append(chunk)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail={"error": "url_timeout", "reason": "Request timed out after 30 s"})
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail={"error": "url_http_error", "reason": str(exc)})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=400, detail={"error": "url_unreachable", "reason": str(exc)})

    raw_bytes = b"".join(chunks)
    if not raw_bytes:
        raise HTTPException(status_code=400, detail={"error": "empty_response", "reason": "Server returned no content"})

    # ---- Detect zip vs single image ----
    job_id = uuid.uuid4()
    tmp_root = os.path.join("tmp_uploads", str(job_id))
    os.makedirs(tmp_root, exist_ok=True)

    if _is_zip(content_type, raw_bytes):
        # ---- Zip branch ----
        zip_path = os.path.join(tmp_root, "import.zip")
        with open(zip_path, "wb") as f:
            f.write(raw_bytes)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                image_names = []
                for name in zf.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in _IMAGE_EXTENSIONS:
                        image_names.append(name)
                    else:
                        if not name.endswith("/"):  # skip directories silently
                            logger.info("import-url: skipping non-image zip entry: %s", name)

                if not image_names:
                    raise HTTPException(
                        status_code=400,
                        detail={"error": "no_images_in_zip", "reason": "Zip contained no supported image files (.jpg, .jpeg, .png, .webp)"},
                    )

                extract_dir = os.path.join(tmp_root, "extracted")
                zf.extractall(extract_dir, members=image_names)

        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail={"error": "invalid_zip", "reason": "File is not a valid zip archive"})

        total = len(image_names)
        async with AsyncSessionLocal() as session:
            job = Job(id=job_id, status="queued", total=total, processed=0)
            session.add(job)
            await session.commit()

        for name in image_names:
            file_path = os.path.join(extract_dir, name)
            safe_name = os.path.basename(name)
            _rq_queue.enqueue(process_image_job, str(job_id), file_path, safe_name, job_timeout=-1)

        logger.info("import-url: zip → %d images queued (job %s)", total, job_id)

    else:
        # ---- Single image branch ----
        # Infer extension from URL path, then content-type, fallback to .jpg
        url_path_ext = os.path.splitext(url.split("?")[0])[-1].lower()
        if url_path_ext in _IMAGE_EXTENSIONS:
            ext = url_path_ext
        elif "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        else:
            ext = ".jpg"

        # Validate it at least starts like an image (basic magic bytes check)
        _IMAGE_MAGIC = {
            b"\xff\xd8\xff": ".jpg",   # JPEG
            b"\x89PNG": ".png",        # PNG
            b"RIFF": ".webp",          # WebP (RIFF container)
        }
        looks_like_image = any(raw_bytes.startswith(m) for m in _IMAGE_MAGIC)
        if not looks_like_image and not ext:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_an_image", "reason": "URL content doesn't appear to be a supported image"},
            )

        filename = f"import{ext}"
        file_path = os.path.join(tmp_root, filename)
        with open(file_path, "wb") as f:
            f.write(raw_bytes)

        total = 1
        async with AsyncSessionLocal() as session:
            job = Job(id=job_id, status="queued", total=total, processed=0)
            session.add(job)
            await session.commit()

        _rq_queue.enqueue(process_image_job, str(job_id), file_path, filename, job_timeout=-1)
        logger.info("import-url: single image queued (job %s)", job_id)

    return {"job_id": str(job_id), "total": total, "status": "queued"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Return Job status. Auto-completes the job if processed == total."""
    async with AsyncSessionLocal() as session:
        try:
            uid = uuid.UUID(job_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid job_id format")

        job = await session.get(Job, uid)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Polling-driven completion: mark complete if all tasks done
        if job.processed >= job.total and job.status in ("queued", "running"):
            job.status = "complete"
            await session.commit()
            await session.refresh(job)

        return {
            "id": str(job.id),
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "error_message": job.error_message,
        }

@app.get("/images/{image_id}/cluster")
async def get_image_cluster(image_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        image = await session.get(Image, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Determine the root image id
        root_id = image.canonical_id if image.canonical_id else image.id
        
        # Load the actual root image row
        root_image = await session.get(Image, root_id)
        if not root_image:
            raise HTTPException(status_code=500, detail="Root image row missing")
            
        # Get the full family
        stmt = select(Image).where(or_(Image.canonical_id == root_id, Image.id == root_id))
        result = await session.execute(stmt)
        family = result.scalars().all()
        
        duplicates = []
        for member in family:
            if member.id == root_id:
                continue
                
            hamming_distance = None
            if root_image.phash and member.phash:
                try:
                    # compute bitwise hamming distance between two length-16 hex strings
                    val1 = int(root_image.phash, 16)
                    val2 = int(member.phash, 16)
                    hamming_distance = bin(val1 ^ val2).count('1')
                except ValueError:
                    pass
            
            similarity = None
            if root_image.embedding and member.embedding:
                # the pg array comes back as a list. Convert to NP array and dot product them.
                v1 = np.array(root_image.embedding)
                v2 = np.array(member.embedding)
                
                # Check for zero norm just to be safe, though they should be l2 normalized
                norm1 = np.linalg.norm(v1)
                norm2 = np.linalg.norm(v2)
                if norm1 > 0 and norm2 > 0:
                    similarity = float(np.dot(v1, v2) / (norm1 * norm2))
            
            duplicates.append({
                "id": str(member.id),
                "filename": member.filename,
                "status": member.status,
                "reason_code": member.reason_code,
                "hamming_distance": hamming_distance,
                "similarity": similarity
            })
            
        # Sort by similarity descending (nulls last)
        duplicates.sort(key=lambda x: x["similarity"] if x["similarity"] is not None else -1.0, reverse=True)
            
        return {
            "root": {
                "id": str(root_image.id),
                "filename": root_image.filename,
                "status": root_image.status
            },
            "duplicates": duplicates,
            "total_duplicates": len(duplicates)
        }


