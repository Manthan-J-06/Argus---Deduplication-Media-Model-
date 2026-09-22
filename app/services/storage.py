import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)


class StorageLimitExceeded(Exception):
    """Raised when an upload would exceed the configured MAX_STORAGE_MB."""
    pass


def _get_dir_size_bytes(directory: str) -> int:
    """Returns the total size in bytes of all files under directory."""
    total = 0
    for dirpath, _, filenames in os.walk(directory):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                total += os.path.getsize(fpath)
            except OSError:
                pass
    return total


def save_file(file_bytes: bytes, sha256: str, original_filename: str) -> str:
    """
    Saves the file to local disk, content-addressed by sha256.
    Deduplicates: if the file already exists, skips the write.
    Enforces MAX_STORAGE_MB cap before writing.
    Returns the file path as a string.
    """
    storage_dir = settings.STORAGE_DIR
    os.makedirs(storage_dir, exist_ok=True)

    _, ext = os.path.splitext(original_filename)
    file_path = os.path.join(storage_dir, f"{sha256}{ext}")

    # 1. Deduplication check
    if os.path.exists(file_path):
        logger.info("File already exists for sha256 %s, skipping write.", sha256)
        return file_path

    # 2. Quota check
    current_size = _get_dir_size_bytes(storage_dir)
    new_total = current_size + len(file_bytes)
    max_bytes = settings.MAX_STORAGE_MB * 1024 * 1024

    if new_total > max_bytes:
        logger.error(
            "Upload rejected: storage %d + %d bytes would exceed cap of %d bytes.",
            current_size, len(file_bytes), max_bytes,
        )
        raise StorageLimitExceeded()

    # 3. Write
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    logger.info("Saved %s to %s.", sha256, file_path)
    return file_path
