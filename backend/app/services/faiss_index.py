import faiss
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Image

class FaissIndexWrapper:
    def __init__(self):
        # IndexFlatIP calculates inner product. 
        # For L2-normalized vectors, inner product == cosine similarity.
        self.index = faiss.IndexIDMap(faiss.IndexFlatIP(512))
        self.id_map = {}  # Map internal FAISS int IDs back to exact UUID strings
        self.current_id = 1

    def add(self, embedding_list: list[float], image_id: str):
        """Add a 512-dim normalized embedding to the index."""
        arr = np.array([embedding_list], dtype=np.float32)
        # Extra safety check, though embeddings should already be normalized
        faiss.normalize_L2(arr)
        
        self.index.add_with_ids(arr, np.array([self.current_id], dtype=np.int64))
        self.id_map[self.current_id] = image_id
        self.current_id += 1

    def search(self, embedding_list: list[float], top_k: int = 5) -> list[dict]:
        """Search the FAISS index and return up to top_k elements."""
        if self.index.ntotal == 0:
            return []
            
        arr = np.array([embedding_list], dtype=np.float32)
        faiss.normalize_L2(arr)
        
        scores, indices = self.index.search(arr, top_k)
        
        results = []
        # scores and indices are 2D arrays, we take the 0th row
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and idx in self.id_map:
                results.append({
                    "id": self.id_map[idx],
                    "similarity": float(score)
                })
        return results

async def load_faiss_from_db(session: AsyncSession) -> FaissIndexWrapper:
    """Load all valid embeddings from the DB into the FAISS index on startup."""
    wrapper = FaissIndexWrapper()
    
    # Only fetch rows that actually have an embedding stored
    stmt = select(Image.id, Image.embedding).where(Image.embedding.isnot(None))
    result = await session.execute(stmt)
    
    count = 0
    for row in result.all():
        img_id_str = str(row[0])
        emb = row[1]
        wrapper.add(emb, img_id_str)
        count += 1
        
    print(f"FAISS loaded {count} vectors.")
    return wrapper
