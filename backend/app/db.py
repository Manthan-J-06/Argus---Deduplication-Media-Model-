from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models import Base  # re-export so alembic can import from here

# Async engine — used by FastAPI request handlers
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine — used by RQ workers (psycopg3 supports sync via the same dialect)
sync_engine = create_engine(settings.DATABASE_URL, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)

__all__ = ["Base", "engine", "AsyncSessionLocal", "sync_engine", "SyncSessionLocal"]
