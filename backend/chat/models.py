"""
SQLAlchemy models for the Chat Layer.

ChatSession  — a named conversation thread tied to a single workspace.
ChatMessage  — a single turn within a session (role: user | assistant).

Design notes
------------
- One workspace can have many sessions (a user may start fresh chats).
- Sessions have an auto-generated title derived from the first user message
  (set by the RAGService after the first turn).
- ChatMessage.sources stores a JSON array of chunk IDs used to ground the
  assistant's answer. This powers the citation panel in the frontend.
- Both tables cascade-delete if the parent is removed (workspace → sessions,
  session → messages).
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Auto-generated from the first user message; updated after first response
    title = Column(String(200), nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "user" or "assistant" — kept as plain string to match OpenAI message format
    role = Column(String(20), nullable=False)
    # Full text content of the message
    content = Column(Text, nullable=False)
    # JSON array of chunk_ids used to ground this answer (empty for user messages)
    sources = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")
