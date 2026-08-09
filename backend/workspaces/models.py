from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class WorkspaceStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class FileStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    PARSED = "parsed"
    CHUNKED = "chunked"
    FAILED = "failed"

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default=WorkspaceStatus.PENDING)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Phase 8 — Metadata Layer
    summary = Column(Text, nullable=True)           # AI-generated workspace overview
    keywords = Column(JSONB, nullable=True)          # List[str] of top keywords
    topics = Column(JSONB, nullable=True)            # List[str] of detected topics
    document_count = Column(Integer, default=0)     # Total non-image files processed
    image_count = Column(Integer, default=0)         # Total image files processed
    total_chunk_count = Column(Integer, default=0)  # Sum of all chunk counts

    owner = relationship("User", back_populates="workspaces")
    files = relationship("File", back_populates="workspace", cascade="all, delete-orphan")

class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    relative_path = Column(String, nullable=False, index=True)
    file_hash = Column(String, nullable=False, index=True)
    mime_type = Column(String, nullable=False)
    size = Column(Integer, nullable=False) # Size in bytes
    status = Column(String, default=FileStatus.PENDING)
    chunk_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Phase 8 — File-level Metadata
    summary = Column(Text, nullable=True)        # AI-generated summary of this file
    keywords = Column(JSONB, nullable=True)       # List[str] extracted from this file
    topics = Column(JSONB, nullable=True)         # List[str] extracted from this file
    page_count = Column(Integer, nullable=True)  # Number of pages/slides (from parser)

    workspace = relationship("Workspace", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    page_number = Column(Integer, nullable=True) # Optional page or slide number
    token_count = Column(Integer, default=0, nullable=False)
    # Structural type detected during indexing. Values: 'text', 'answer_key',
    # 'table', 'toc', 'reference', 'code'. Defaults to 'text' for all legacy chunks.
    chunk_type = Column(String, nullable=False, default="text", server_default="text")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    file = relationship("File", back_populates="chunks")
