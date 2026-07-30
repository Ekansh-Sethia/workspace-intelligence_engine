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

    class Config:
        from_attributes = True
