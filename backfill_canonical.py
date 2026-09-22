import uuid
from app.db import SyncSessionLocal
from app.models import Image
from app.worker import _resolve_canonical_sync

def backfill():
    with SyncSessionLocal() as session:
        # Get all rows that HAVE a canonical_id
        images = session.query(Image).filter(Image.canonical_id.isnot(None)).all()
        
        checked = len(images)
        updated = 0
        already_correct = 0
        
        for img in images:
            # We want to resolve the root of img's CURRENT canonical_id
            # So we pass the parent image to _resolve_canonical_sync
            
            # _resolve_canonical_sync takes a matched_image and traverses up
            current_canonical = img.canonical_id
            
            # We fetch the parent to walk from
            parent = session.query(Image).filter(Image.id == current_canonical).first()
            if not parent:
                # Dangling reference, can't resolve further
                continue
                
            root_id = _resolve_canonical_sync(session, parent)
            
            if root_id != img.canonical_id:
                print(f"UPDATED {img.filename} ({img.id}): canonical_id {img.canonical_id} -> {root_id}")
                img.canonical_id = root_id
                updated += 1
            else:
                already_correct += 1
                
        session.commit()
        print(f"\nSummary:")
        print(f"Rows checked: {checked}")
        print(f"Rows updated: {updated}")
        print(f"Rows already correct: {already_correct}")

if __name__ == "__main__":
    backfill()
