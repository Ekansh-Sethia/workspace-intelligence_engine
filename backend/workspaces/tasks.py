import asyncio
from worker import celery_app
from core.database import AsyncSessionLocal, engine
from workspaces.models import Workspace, WorkspaceStatus, File, FileStatus, Chunk
import authentication.models  # Required to register User model for SQLAlchemy relationships
from workspaces.utils import secure_extract, scan_and_process_workspace
from workspaces.metadata import MetadataService
from chunking.tokenizer import TiktokenTokenizer
from chunking.splitter import DocumentChunker
from chunking.classifier import classify_chunk
from parsers.factory import get_parser
from embeddings import FastEmbedProvider
from embeddings.service import EmbeddingService
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

async def parse_and_chunk_workspace_files(workspace_id: int, raw_dir: Path):
    """
    Parse and chunk every extracted file in the workspace.

    Each file is parsed and chunked independently. The raw text is kept
    in memory just long enough to be chunked and then discarded. 
    On success, the file status becomes CHUNKED; on failure it becomes FAILED.
    """
    
    tokenizer = TiktokenTokenizer()
    chunker = DocumentChunker(tokenizer=tokenizer)
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
                
                # Immediately chunk the document while text is in memory
                raw_chunks = chunker.chunk_document(doc)
                
                db_chunks = [
                    Chunk(
                        file_id=file_record.id,
                        chunk_index=c["chunk_index"],
                        text=c["text"],
                        page_number=c["page_number"],
                        token_count=c["token_count"],
                        chunk_type=classify_chunk(c["text"]),
                    )
                    for c in raw_chunks
                ]
                
                db.add_all(db_chunks)
                file_record.chunk_count = len(db_chunks)
                file_record.status = FileStatus.CHUNKED
                parsed_count += 1
                logger.info(
                    f"Parsed and chunked '{file_record.relative_path}' "
                    f"({len(doc.text)} chars, {len(db_chunks)} chunks)"
                )
            except Exception as exc:
                file_record.status = FileStatus.FAILED
                failed_count += 1
                logger.warning(
                    f"Failed to parse '{file_record.relative_path}': {exc}"
                )

        await db.commit()
        logger.info(
            f"Workspace {workspace_id} parse/chunk complete: "
            f"{parsed_count} succeeded, {failed_count} failed"
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
        
        # Make extraction idempotent for Celery retries
        if not zip_path.exists():
            if any(raw_dir.iterdir()):
                logger.info("ZIP file already extracted in previous attempt, skipping extraction.")
            else:
                raise ValueError(f"ZIP file not found at {zip_file_path} and raw directory is empty.")
        else:
            if not zipfile.is_zipfile(zip_path):
                raise ValueError("Uploaded file is not a valid ZIP archive")
                
            # 2. Secure Extract ZIP (Zip Slip protected)
            secure_extract(zip_path, raw_dir)
        
        # 4. Scan, filter, hash, and create File database records
        async with AsyncSessionLocal() as db:
            await scan_and_process_workspace(workspace_id, raw_dir, db)

        # 5. Parse and chunk all extracted files (Phases 5 & 6)
        await parse_and_chunk_workspace_files(workspace_id, raw_dir)
        
        # 6. Generate embeddings and store in Qdrant (Phase 7)
        provider = FastEmbedProvider()
        service = EmbeddingService(provider=provider)
        async with AsyncSessionLocal() as db:
            total_vectors = await service.embed_and_store_workspace(workspace_id, db)
        logger.info(f"Workspace {workspace_id}: {total_vectors} vectors stored in Qdrant")
        
        # 7. Generate AI metadata for all files + workspace roll-up (Phase 8)
        async with AsyncSessionLocal() as db:
            metadata_service = MetadataService()
            await metadata_service.generate_for_workspace(workspace_id, db)
        
        # 8. Update status to ready
        await update_workspace_status(workspace_id, WorkspaceStatus.READY)
        
        # 8. Cleanup the raw zip file to save space only on success
        if zip_path.exists():
            os.remove(zip_path)
            
        logger.info(f"Successfully processed workspace {workspace_id}")
        return None
    except Exception as exc:
        logger.error(f"Failed to process workspace {workspace_id}: {exc}")
        
        await update_workspace_status(workspace_id, WorkspaceStatus.FAILED)
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

