import hashlib
import io
import imagehash
from PIL import Image


def compute_sha256(file_bytes: bytes) -> str:
    """Return the lowercase hex digest of the file's SHA-256."""
    return hashlib.sha256(file_bytes).hexdigest()

def compute_phash(file_bytes: bytes) -> str:
    """Return the perceptual hash (16-char hex) of the image."""
    img = Image.open(io.BytesIO(file_bytes))
    return str(imagehash.phash(img))
