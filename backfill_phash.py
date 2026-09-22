import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.services.hashing import compute_phash

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.db import AsyncSessionLocal
from app.services.hashing import compute_phash

async def backfill():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id, filename FROM images WHERE phash = '0000000000000000'"))
        rows = result.fetchall()
        print(f"Found {len(rows)} rows to backfill")
        
        for row in rows:
            try:
                with open(row[1], 'rb') as f:
                    h = compute_phash(f.read())
                print(f"Updating {row[1]} to phash {h}")
                await session.execute(
                    text("UPDATE images SET phash = :phash WHERE id = :id"),
                    {"phash": h, "id": row[0]}
                )
            except Exception as e:
                print(f"Skipping {row[1]}: {e}")
                
        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(backfill())
