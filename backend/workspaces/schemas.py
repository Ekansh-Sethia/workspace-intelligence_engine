from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None


class WorkspaceResponse(BaseModel):
    """Lightweight response for workspace listing."""
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    owner_id: int
    # Phase 8 metadata — nullable until processing completes
    summary: Optional[str] = None
    topics: Optional[list] = None
    document_count: int = 0
    image_count: int = 0
    total_chunk_count: int = 0
    # Computed at query time — total number of files in the workspace
    file_count: Optional[int] = None

    model_config = {"from_attributes": True}


class WorkspaceDetailResponse(WorkspaceResponse):
    """Full detail response including keywords."""
    keywords: Optional[list] = None

    model_config = {"from_attributes": True}


class FileResponse(BaseModel):
    id: int
    workspace_id: int
    relative_path: str
    file_hash: str
    mime_type: str
    size: int
    status: str
    chunk_count: int = 0
    created_at: datetime
    # Phase 8 metadata — nullable until processing completes
    summary: Optional[str] = None
    keywords: Optional[list] = None
    topics: Optional[list] = None
    page_count: Optional[int] = None

    model_config = {"from_attributes": True}
