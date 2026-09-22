import pybktree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Image

def hamming_distance(hex1: str, hex2: str) -> int:
    """Calculate hamming distance between two hex strings."""
    # Convert hex strings to integers, XOR them, and count the 1s (popcount)
    return bin(int(hex1, 16) ^ int(hex2, 16)).count('1')

async def load_bktree_from_db(session: AsyncSession) -> pybktree.BKTree:
    """Load all existing phashes from DB and build a BKTree."""
    tree = pybktree.BKTree(hamming_distance)
    
    # Query all phashes. Exclude the placeholder if it exists.
    stmt = select(Image.phash).where(Image.phash != "0000000000000000")
    result = await session.execute(stmt)
    
    count = 0
    for row in result.all():
        phash = row[0]
        tree.add(phash)
        count += 1
        
    print(f"BK-tree loaded with {count} phashes.")
    return tree

def find_near_duplicates(tree: pybktree.BKTree, phash: str, max_distance: int = 8) -> list[tuple[int, str]]:
    """Return all phashes in tree within max_distance of target phash."""
    if not tree:
        return []
    return tree.find(phash, max_distance)

def insert_into_bktree(tree: pybktree.BKTree, phash: str) -> None:
    """Insert a single new phash into the live tree."""
    tree.add(phash)
