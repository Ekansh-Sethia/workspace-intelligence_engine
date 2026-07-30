from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from core.database import get_db
from authentication.dependencies import get_current_user
from authentication.models import User
from workspaces.models import Workspace, WorkspaceStatus
from workspaces.schemas import WorkspaceResponse
from workspaces.services import delete_workspace_storage
from workspaces.tasks import process_workspace_upload
import os
import shutil
from pathlib import Path

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Workspace).where(Workspace.owner_id == current_user.id))
    return result.scalars().all()

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_workspace(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 50MB size limit check (approx)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")
        
    # Create DB entry first to get ID
    new_workspace = Workspace(
        name=name,
        description=description,
        owner_id=current_user.id,
        status=WorkspaceStatus.PENDING
    )
    db.add(new_workspace)
    await db.commit()
    await db.refresh(new_workspace)
    
    # Save the raw ZIP file temporarily for the worker
    ws_dir = Path("local_storage") / str(new_workspace.id)
    os.makedirs(ws_dir, exist_ok=True)
    zip_path = ws_dir / "archive.zip"
    
    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        await db.delete(new_workspace)
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to save file for processing")
        
    # Trigger Celery Task (Pass the file path, not the File object)
    process_workspace_upload.delay(new_workspace.id, str(zip_path))
    
    return new_workspace

@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id))
    workspace = result.scalars().first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Delete from DB (cascade rules will handle relations if any)
    await db.delete(workspace)
    await db.commit()
    
    # Delete local files
    delete_workspace_storage(workspace.id)
