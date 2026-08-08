"""
Pydantic schemas for the Chat Layer API.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any


class ChatSessionCreate(BaseModel):
    """Request body to start a new chat session."""
    # Optional: caller may supply a title; if omitted, it is auto-generated
    title: str | None = Field(default=None, max_length=200)


class ChatSessionResponse(BaseModel):
    """Session metadata returned to the client."""
    id: int
    workspace_id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """A single message turn returned from the history endpoint."""
    id: int
    session_id: int
    role: str
    content: str
    sources: list[Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Request body for sending a user message and receiving a streamed answer."""
    query: str = Field(..., min_length=1, max_length=4000, description="User's natural language question")


class SessionHistoryResponse(BaseModel):
    """Full session with all messages — used by the history endpoint."""
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]
