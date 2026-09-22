import uuid
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Image

logger = logging.getLogger(__name__)


async def check_exact_duplicate(session: AsyncSession, sha256: str):
    """Query for an existing image with a matching sha256. Returns Image or None."""
    stmt = select(Image).where(Image.sha256 == sha256).limit(1)
    result = await session.execute(stmt)
    return result.scalars().first()


async def resolve_canonical_id(session: AsyncSession, matched_image: Image) -> uuid.UUID:
    """
    Walk the canonical_id chain until reaching a row whose canonical_id is None
    (the true root/original accepted image). Capped at 20 hops: raises RuntimeError
    if the cap is hit, so a malformed chain is never silently swallowed.
    """
    current = matched_image
    hops = 0
    while current.canonical_id is not None:
        if hops >= 20:
            raise RuntimeError(
                f"resolve_canonical_id: chain depth exceeded 20 hops starting from "
                f"{matched_image.id} — possible cycle or deeply nested duplicates. "
                f"Last visited id: {current.id}"
            )
        parent = await session.get(Image, current.canonical_id)
        if parent is None:
            # Dangling FK — log and stop here rather than crash
            logger.warning(
                "resolve_canonical_id: canonical_id %s on row %s points to a "
                "non-existent row; using %s as canonical.",
                current.canonical_id, current.id, current.id,
            )
            break
        current = parent
        hops += 1

    logger.debug("resolve_canonical_id: resolved in %d hop(s) → %s", hops, current.id)
    return current.id
