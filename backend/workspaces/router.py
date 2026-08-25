from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional

from core.database import get_db
from authentication.dependencies import get_current_user
from authentication.models import User
from workspaces.models import Workspace, WorkspaceStatus, File as FileModel
from workspaces.schemas import WorkspaceResponse, WorkspaceDetailResponse, FileResponse
from workspaces.search_schemas import SearchQuery, SearchResult
from workspaces.tasks import process_workspace_upload
from workspaces.actions import ActionService
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


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return full detail for a single workspace, including Phase 8 metadata."""
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    # Compute file_count dynamically so it is always accurate
    count_result = await db.execute(
        select(func.count(FileModel.id)).where(FileModel.workspace_id == workspace_id)
    )
    workspace.file_count = count_result.scalar() or 0
    return workspace


@router.get("/{workspace_id}/summary")
async def get_workspace_summary(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the AI-generated summary, topics, and keywords for a workspace."""
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {
        "workspace_id": workspace.id,
        "name": workspace.name,
        "summary": workspace.summary,
        "keywords": workspace.keywords or [],
        "topics": workspace.topics or [],
        "document_count": workspace.document_count,
        "image_count": workspace.image_count,
        "total_chunk_count": workspace.total_chunk_count,
    }

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
    import zipfile
    import io
    import hashlib
    import mimetypes
    from utils.logger import logger
    
    try:
        # Read the raw ZIP bytes
        file.file.seek(0)
        zip_bytes = file.file.read()
        
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for zip_info in z.infolist():
                if zip_info.is_dir():
                    continue
                
                # Protect against Zip Slip in memory
                if ".." in zip_info.filename or zip_info.filename.startswith("/") or zip_info.filename.startswith("\\"):
                    continue
                
                # Ignore macOS __MACOSX directories and hidden files
                if "__MACOSX" in zip_info.filename or os.path.basename(zip_info.filename).startswith("."):
                    continue
                
                # Extract file contents
                file_content = z.read(zip_info.filename)
                
                # Calculate file hash
                file_hash = hashlib.sha256(file_content).hexdigest()
                
                # Guess mime type
                mime_type, _ = mimetypes.guess_type(zip_info.filename)
                if not mime_type:
                    mime_type = "application/octet-stream"
                
                # Create File record
                new_file = FileModel(
                    workspace_id=new_workspace.id,
                    relative_path=zip_info.filename,
                    file_hash=file_hash,
                    content=file_content,
                    mime_type=mime_type,
                    size=len(file_content)
                )
                db.add(new_file)
        
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to process zip in-memory: {e}")
        await db.delete(new_workspace)
        await db.commit()
        raise HTTPException(status_code=500, detail="Failed to save file for processing")
        
    # Trigger Celery Task (Pass workspace_id only, no disk paths)
    process_workspace_upload.delay(new_workspace.id)
    
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


# ── Phase 13: Workspace Actions ───────────────────────────────────────────────

@router.get("/{workspace_id}/export")
async def export_workspace(
    workspace_id: int,
    format: str = Query(default="txt", pattern="^(txt|md)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Download the entire workspace as a single merged TXT or Markdown file.
    All text is sourced from parsed+chunked Postgres records.
    """
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id, Workspace.owner_id == current_user.id
        )
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.status != "ready":
        raise HTTPException(status_code=409, detail="Workspace is not ready")

    action_service = ActionService(db=db)
    content = await action_service.export_workspace(workspace_id, format=format)
    ext = "md" if format == "md" else "txt"
    filename = f"{workspace.name.replace(' ', '_')}_export.{ext}"
    media_type = "text/markdown" if format == "md" else "text/plain"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{workspace_id}/actions/quiz", response_class=StreamingResponse)
async def generate_quiz(
    workspace_id: int,
    file_id: Optional[int] = Query(default=None, description="Specific file ID to quiz on"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a 5-question MCQ quiz from a file or the whole workspace.
    Streams the quiz as SSE.
    """
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id, Workspace.owner_id == current_user.id
        )
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.status != "ready":
        raise HTTPException(status_code=409, detail="Workspace is not ready")

    action_service = ActionService(db=db)
    return StreamingResponse(
        action_service.generate_quiz(workspace_id, file_id=file_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{workspace_id}/actions/notes", response_class=StreamingResponse)
async def generate_notes(
    workspace_id: int,
    file_id: Optional[int] = Query(default=None, description="Specific file ID to summarise"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate structured revision notes from a file or the whole workspace.
    Streams the notes as SSE.
    """
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id, Workspace.owner_id == current_user.id
        )
    )
    workspace = ws_result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.status != "ready":
        raise HTTPException(status_code=409, detail="Workspace is not ready")

    action_service = ActionService(db=db)
    return StreamingResponse(
        action_service.generate_notes(workspace_id, file_id=file_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
