import asyncio
from worker import celery_app
from core.database import AsyncSessionLocal, engine
from workspaces.models import Workspace, WorkspaceStatus, File, FileStatus, Chunk
import authentication.models  # Required to register User model for SQLAlchemy relationships
from workspaces.metadata import MetadataService
from chunking.tokenizer import TiktokenTokenizer
from chunking.splitter import DocumentChunker
from chunking.classifier import classify_chunk
from parsers.factory import get_parser
from embeddings import FastEmbedProvider
from embeddings.service import EmbeddingService
from utils.logger import logger
from pathlib import Path
from sqlalchemy import select

async def update_workspace_status(workspace_id: int, status: WorkspaceStatus):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if workspace:
            workspace.status = status
            await db.commit()

async def parse_and_chunk_workspace_files(workspace_id: int):
    """
    Parse and chunk every extracted file in the workspace directly from DB.

    Each file is parsed and chunked independently. 
    On success, the file status becomes CHUNKED; on failure it becomes FAILED.
    """
    
    tokenizer = TiktokenTokenizer()
    chunker = DocumentChunker(tokenizer=tokenizer)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(File).where(
                File.workspace_id == workspace_id,
                File.status == FileStatus.PENDING,
            )
        )
        files = result.scalars().all()

        parsed_count = 0
        failed_count = 0

        for file_record in files:
            ext = Path(file_record.relative_path).suffix.lower()

            try:
                parser = get_parser(ext)
                # Pass raw bytes directly from the database to the parser
                doc = parser.parse(file_content=file_record.content, filename=file_record.relative_path, source_path=file_record.relative_path)
                
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

async def run_processing(workspace_id: int):
    try:
        # Update status to processing
        await update_workspace_status(workspace_id, WorkspaceStatus.PROCESSING)
        
        # 1. Parse and chunk all uploaded files directly from DB
        await parse_and_chunk_workspace_files(workspace_id)
        
        # 2. Generate embeddings and store in Qdrant
        provider = FastEmbedProvider()
        service = EmbeddingService(provider=provider)
        async with AsyncSessionLocal() as db:
            total_vectors = await service.embed_and_store_workspace(workspace_id, db)
        logger.info(f"Workspace {workspace_id}: {total_vectors} vectors stored in Qdrant")
        
        # 3. Generate AI metadata for all files + workspace roll-up
        async with AsyncSessionLocal() as db:
            metadata_service = MetadataService()
            await metadata_service.generate_for_workspace(workspace_id, db)
        
        # 4. Update status to ready
        await update_workspace_status(workspace_id, WorkspaceStatus.READY)
            
        logger.info(f"Successfully processed workspace {workspace_id}")
        return None
    except Exception as exc:
        logger.error(f"Failed to process workspace {workspace_id}: {exc}")
        
        await update_workspace_status(workspace_id, WorkspaceStatus.FAILED)
        return exc
    finally:
        # Only dispose engine if running as an isolated Celery worker process
        if not getattr(settings, "RUN_CELERY_IN_PROCESS", True):
            await engine.dispose()

import threading
from utils.config import settings

@celery_app.task(bind=True, max_retries=3)
def _celery_process_workspace_upload(self, workspace_id: int):
    """
    Celery task to parse the workspace files directly from the database in the background.
    """
    logger.info(f"Starting Celery background processing for workspace {workspace_id}")
    
    exc = asyncio.run(run_processing(workspace_id))
    
    # Retry with exponential backoff if it wasn't a validation error
    if exc is not None and not isinstance(exc, ValueError):
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


class _TaskDispatcher:
    def __init__(self, celery_task):
        self._celery_task = celery_task

    def delay(self, workspace_id: int):
        if getattr(settings, "RUN_CELERY_IN_PROCESS", True):
            logger.info(f"Dispatching workspace {workspace_id} processing to in-process task")
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(run_processing(workspace_id))
            except RuntimeError:
                # If called synchronously outside an active event loop
                asyncio.run(run_processing(workspace_id))
            return None
        return self._celery_task.delay(workspace_id)

    def __call__(self, *args, **kwargs):
        return self._celery_task(*args, **kwargs)


process_workspace_upload = _TaskDispatcher(_celery_process_workspace_upload)
