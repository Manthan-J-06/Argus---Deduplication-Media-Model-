import time
from PIL import Image
from sentence_transformers import SentenceTransformer
import numpy as np

# Module-level singleton: Ensure the model is loaded exactly once at import
_model = SentenceTransformer('clip-ViT-B-32')

def compute_embedding(image: Image.Image) -> list[float]:
    """
    Encode a single image via CLIP.
    L2-normalize the vector and return it as a pure Python list of 512 floats.
    """
    start_t = time.perf_counter()
    
    # SentenceTransformer encode natively returns a NumPy array
    emb = _model.encode(image)
    
    # Ensure it is a 1-dimensional array before normalization
    emb = np.array(emb).flatten()
    
    # Calculate vector magnitude and L2-normalize
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
        
    # Cast entirely back to native floats for system consumption
    result = emb.tolist()
    
    elapsed = time.perf_counter() - start_t
    print(f"Embedding computed in {elapsed:.3f}s")
    
    return result
