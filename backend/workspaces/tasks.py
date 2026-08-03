import asyncio
from worker import celery_app
from core.database import AsyncSessionLocal, engine
from workspaces.models import Workspace, WorkspaceStatus, File, FileStatus
import authentication.models  # Required to register User model for SQLAlchemy relationships
from workspaces.utils import secure_extract, scan_and_process_workspace
from parsers.factory import get_parser
from utils.logger import logger
import os
import shutil
import zipfile
from pathlib import Path
from sqlalchemy import select

STORAGE_DIR = Path("local_storage")

async def update_workspace_status(workspace_id: int, status: WorkspaceStatus):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if workspace:
            workspace.status = status
            await db.commit()

async def parse_workspace_files(workspace_id: int, raw_dir: Path):
    """
    Parse every extracted file in the workspace.

    Each file is parsed independently — a failure in one file does NOT
    affect the others.  On success the file status becomes PARSED; on
    failure it becomes FAILED and the error is logged.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(File).where(
                File.workspace_id == workspace_id,
                File.status == FileStatus.EXTRACTED,
            )
        )
        files = result.scalars().all()

        parsed_count = 0
        failed_count = 0

        for file_record in files:
            filepath = raw_dir / file_record.relative_path
            ext = Path(file_record.relative_path).suffix.lower()

            try:
                parser = get_parser(ext)
                doc = parser.parse(filepath, source_path=file_record.relative_path)
                file_record.status = FileStatus.PARSED
                parsed_count += 1
                logger.info(
                    f"Parsed '{file_record.relative_path}' "
                    f"({len(doc.text)} chars, {doc.page_count} pages)"
                )
            except Exception as exc:
                file_record.status = FileStatus.FAILED
                failed_count += 1
                logger.warning(
                    f"Failed to parse '{file_record.relative_path}': {exc}"
                )

        await db.commit()
        logger.info(
            f"Workspace {workspace_id} parsing complete: "
            f"{parsed_count} parsed, {failed_count} failed"
        )

async def run_processing(workspace_id: int, zip_file_path: str):
    try:
        # Update status to processing
        await update_workspace_status(workspace_id, WorkspaceStatus.PROCESSING)
        
        # 1. Setup directories
        ws_dir = STORAGE_DIR / str(workspace_id)
        raw_dir = ws_dir / "raw"
        os.makedirs(raw_dir, exist_ok=True)
        
        zip_path = Path(zip_file_path)
        
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Uploaded file is not a valid ZIP archive")
            
        # 2. Secure Extract ZIP (Zip Slip protected)
        secure_extract(zip_path, raw_dir)
            
        # 3. Cleanup the raw zip file to save space
        os.remove(zip_path)
        
        # 4. Scan, filter, hash, and create File database records
        async with AsyncSessionLocal() as db:
            await scan_and_process_workspace(workspace_id, raw_dir, db)

        # 5. Parse all extracted files (Phase 5)
        await parse_workspace_files(workspace_id, raw_dir)
        
        # 6. Update status to ready
        await update_workspace_status(workspace_id, WorkspaceStatus.READY)
        logger.info(f"Successfully processed workspace {workspace_id}")
        return None
    except Exception as exc:
        logger.error(f"Failed to process workspace {workspace_id}: {exc}")
        
        await update_workspace_status(workspace_id, WorkspaceStatus.FAILED)
            
        # Cleanup broken files
        ws_dir = STORAGE_DIR / str(workspace_id)
        shutil.rmtree(ws_dir, ignore_errors=True)
        return exc
    finally:
        # Crucial: Close all database connections tied to this event loop
        await engine.dispose()

@celery_app.task(bind=True, max_retries=3)
def process_workspace_upload(self, workspace_id: int, zip_file_path: str):
    """
    Celery task to extract and parse the workspace ZIP file in the background.
    """
    logger.info(f"Starting background processing for workspace {workspace_id}")
    
    exc = asyncio.run(run_processing(workspace_id, zip_file_path))
    
    # Retry with exponential backoff if it wasn't a validation error
    if exc is not None and not isinstance(exc, ValueError):
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

