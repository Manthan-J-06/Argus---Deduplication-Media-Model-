"""
Diagnostic sweep: transforms of test_photo2.jpg vs base phash + CLIP embedding.
Prints a table of hamming_distance and cosine_similarity for 8 variants.
Run from the argus/ directory: python sweep_thresholds.py
"""
import io
import math
import imagehash
import numpy as np
from PIL import Image

# Import the CLIP singleton (loads model once at module level)
from app.services.embedding import compute_embedding

BASE_PHASH_HEX = "c7c7231b2d4d923a"
BASE_PATH = "test_photo2.jpg"

def hamming(h1_hex: str, h2_hex: str) -> int:
    a = int(h1_hex, 16)
    b = int(h2_hex, 16)
    return bin(a ^ b).count("1")

def cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    # Both are already L2-normalised, so dot product == cosine similarity
    return float(np.dot(va, vb))

def phash_hex(img: Image.Image) -> str:
    return str(imagehash.phash(img))

# Load base image and compute base embedding once
base_img = Image.open(BASE_PATH)
print("Computing base CLIP embedding…")
base_emb = compute_embedding(base_img)
print("Done.\n")

# Define variants
variants = []

# JPEG quality variants
for q in [90, 70, 50, 30, 10]:
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG", quality=q)
    buf.seek(0)
    img = Image.open(buf)
    img.load()  # force decode before BytesIO is recycled
    variants.append((f"jpeg_q{q:02d}", img))

# Rotation variants
for deg in [2, 5, 10]:
    img = base_img.rotate(deg)
    variants.append((f"rotate_{deg}deg", img))

# Header
print(f"{'variant':<22} | {'hamming':>7} | {'cosine_sim':>10}")
print("-" * 45)

for name, img in variants:
    ph = phash_hex(img)
    hd = hamming(BASE_PHASH_HEX, ph)
    emb = compute_embedding(img)
    cs = cosine(base_emb, emb)
    print(f"{name:<22} | {hd:>7} | {cs:>10.6f}")
