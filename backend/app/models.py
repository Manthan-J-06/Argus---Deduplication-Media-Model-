import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Image(Base):
    __tablename__ = "images"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    phash = Column(String(16), nullable=False, index=True)
    embedding = Column(ARRAY(Float), nullable=True)
    status = Column(String, nullable=False, default="pending")
    reason_code = Column(String, nullable=True)
    canonical_id = Column(Uuid, ForeignKey("images.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_by_human = Column(Boolean, nullable=False, default=False, server_default="false")
    reviewed_at = Column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    status = Column(String, nullable=False, default="queued")
    total = Column(Integer, nullable=False, default=0)
    processed = Column(Integer, nullable=False, default=0)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
