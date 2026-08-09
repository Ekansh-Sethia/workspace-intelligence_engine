"""
Pydantic schemas for the Semantic Search endpoint.
"""
from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Request body for the workspace search endpoint."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language search query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results to return")


class SearchResult(BaseModel):
    """A single search result returned from Qdrant."""
    score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")
    text: str = Field(..., description="The raw chunk text")
    file_id: int
    chunk_id: int
    chunk_index: int
    page_number: int | None = None
    # Structural type detected at index time: 'text', 'answer_key', 'table', etc.
    chunk_type: str = "text"
