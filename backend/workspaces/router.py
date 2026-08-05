from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from core.database import get_db
from authentication.dependencies import get_current_user
from authentication.models import User
from workspaces.models import Workspace, WorkspaceStatus, File as FileModel
from workspaces.schemas import WorkspaceResponse, FileResponse
from workspaces.search_schemas import SearchQuery, SearchResult
from workspaces.services import delete_workspace_storage
from workspaces.tasks import process_workspace_upload
from embeddings import FastEmbedProvider
from embeddings.service import EmbeddingService
from embeddings.search import SearchService
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
        
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        
    # Quick synchronous check to ensure it's actually a valid ZIP file
    import zipfile
    if not zipfile.is_zipfile(file.file):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive or is corrupt.")
    
    # Reset pointer after zipfile check
    file.file.seek(0)
        
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
    
    # Delete vectors from Qdrant (best-effort, don't fail if Qdrant is unavailable)
    try:
        service = EmbeddingService(provider=FastEmbedProvider())
        service.delete_workspace_vectors(workspace.id)
    except Exception as e:
        from utils.logger import logger
        logger.warning(f"Failed to delete Qdrant vectors for workspace {workspace_id}: {e}")

@router.get("/{workspace_id}/files", response_model=List[FileResponse])
async def get_workspace_files(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify workspace ownership first
    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id))
    workspace = ws_result.scalars().first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # Get all files for this workspace
    result = await db.execute(select(FileModel).where(FileModel.workspace_id == workspace_id))
    return result.scalars().all()


@router.post("/{workspace_id}/search", response_model=list[SearchResult])
async def search_workspace(
    workspace_id: int,
    body: SearchQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform a semantic similarity search against a workspace's indexed chunks.
    Returns ranked chunks ordered by cosine similarity to the query.
    """
    # Enforce ownership — users can only search their own workspaces
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id
        )
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Workspace is not ready for search (current status: {workspace.status})"
        )

    service = SearchService(provider=FastEmbedProvider())
    return service.search(
        workspace_id=workspace_id,
        query=body.query,
        limit=body.limit,
    )
