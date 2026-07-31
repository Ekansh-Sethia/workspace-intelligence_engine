from pydantic import BaseModel
from datetime import datetime
from workspaces.models import WorkspaceStatus

class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None

class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    owner_id: int

    model_config = {"from_attributes": True}

class FileResponse(BaseModel):
    id: int
    workspace_id: int
    relative_path: str
    file_hash: str
    mime_type: str
    size: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
