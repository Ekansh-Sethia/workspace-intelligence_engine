"""
MetadataService - Phase 8

Generates AI-powered metadata for files and workspaces after the embedding
pipeline completes. Uses llm_complete to generate summaries, keywords, topics.

Graceful degradation: LLM failure for one file does not affect the workspace.
"""
import json
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from workspaces.models import Workspace, File
from llm.gateway import llm_complete
from utils.logger import logger


_FILE_SUMMARY_SYSTEM = (
    "You are a precise document analyst. Given a sample of text from a document, "
    "produce a concise metadata object. "
    "Return ONLY a valid JSON object with exactly these three keys: "
    '"summary" (2-3 sentences about the document), '
    '"keywords" (JSON array of 5-8 keyword strings), '
    '"topics" (JSON array of 2-4 topic label strings). '
    "No markdown fences or explanation, only the JSON."
)

_WORKSPACE_SUMMARY_SYSTEM = (
    "You are a workspace analyst. Given per-file summaries, produce a workspace overview. "
    "Return ONLY a valid JSON object with exactly these three keys: "
    '"summary" (3-4 sentence overview), '
    '"keywords" (JSON array of 8-12 keyword strings), '
    '"topics" (JSON array of 3-6 topic label strings). '
    "No markdown fences or explanation, only the JSON."
)


def _sample_text(text: str, max_chars: int = 3000) -> str:
    """Return the first max_chars characters of text for the LLM prompt."""
    return text[:max_chars].strip()


async def _parse_metadata_response(raw: str) -> Optional[dict]:
    """Safely parse the LLM JSON response. Returns None on parse error."""
    try:
        cleaned = raw.strip().strip("`").strip("json").strip("`").strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"MetadataService: failed to parse LLM JSON: {exc!r}")
        return None


class MetadataService:
    """Generates AI metadata for every file in a workspace, then rolls it up."""

    async def generate_for_file(self, file_record: File, db: AsyncSession) -> None:
        """Read file chunks from Postgres, send sample to LLM, persist metadata."""
        from workspaces.models import Chunk
        result = await db.execute(
            select(Chunk.text)
            .where(Chunk.file_id == file_record.id)
            .order_by(Chunk.chunk_index)
            .limit(8)
        )
        chunk_texts = result.scalars().all()

        if not chunk_texts:
            logger.warning(f"MetadataService: no chunks for file {file_record.id}, skipping.")
            return

        sample = _sample_text("\n\n".join(chunk_texts))
        try:
            raw_response = await llm_complete(
                system_prompt=_FILE_SUMMARY_SYSTEM,
                user_message=f"Document text sample:\n\n{sample}",
                max_tokens=400,
            )
            metadata = await _parse_metadata_response(raw_response)
            if metadata:
                file_record.summary = metadata.get("summary")
                file_record.keywords = metadata.get("keywords", [])
                file_record.topics = metadata.get("topics", [])
                logger.info(f"MetadataService: metadata OK for file {file_record.id}")
        except Exception as exc:
            logger.warning(f"MetadataService: LLM failed for file {file_record.id}: {exc!r}")

    async def generate_for_workspace(self, workspace_id: int, db: AsyncSession) -> None:
        """Generate per-file metadata then roll up into a workspace-level summary."""
        logger.info(f"MetadataService: starting for workspace {workspace_id}")

        ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = ws_result.scalar_one_or_none()
        if not workspace:
            logger.error(f"MetadataService: workspace {workspace_id} not found")
            return

        files_result = await db.execute(select(File).where(File.workspace_id == workspace_id))
        files = files_result.scalars().all()

        doc_count, img_count, total_chunks = 0, 0, 0
        for file_record in files:
            if not file_record.mime_type.startswith("image/"):
                await self.generate_for_file(file_record, db)
                doc_count += 1
            else:
                img_count += 1
            total_chunks += file_record.chunk_count or 0

        await db.commit()

        file_summaries = [
            f"File: {os.path.basename(f.relative_path)}\nSummary: {f.summary}"
            for f in files if f.summary
        ]

        if file_summaries:
            sample = _sample_text("\n\n".join(file_summaries), max_chars=4000)
            try:
                raw_response = await llm_complete(
                    system_prompt=_WORKSPACE_SUMMARY_SYSTEM,
                    user_message=f"File summaries:\n\n{sample}",
                    max_tokens=600,
                )
                ws_metadata = await _parse_metadata_response(raw_response)
                if ws_metadata:
                    workspace.summary = ws_metadata.get("summary")
                    workspace.keywords = ws_metadata.get("keywords", [])
                    workspace.topics = ws_metadata.get("topics", [])
            except Exception as exc:
                logger.warning(f"MetadataService: workspace roll-up failed: {exc!r}")

        workspace.document_count = doc_count
        workspace.image_count = img_count
        workspace.total_chunk_count = total_chunks
        await db.commit()
        logger.info(f"MetadataService: workspace {workspace_id} complete")
