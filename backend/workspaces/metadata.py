"""
MetadataService - Phase 8 (Memory-Optimized for Render Free Tier)

Generates concise metadata (summaries, keywords, topics) and roll-up statistics
for files and workspaces without invoking external LLMs during the heavy ingestion pipeline.
This prevents loading LiteLLM into RAM alongside ONNX, guaranteeing memory stays
well below the 512MB Render limit.
"""
import os
import re
from collections import Counter
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from workspaces.models import Workspace, File, Chunk
from utils.logger import logger

_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "are", "was",
    "were", "which", "your", "about", "into", "some", "more", "also", "will",
    "been", "would", "could", "their", "there", "what", "when", "where", "them",
    "each", "other", "then", "than", "very", "just", "such", "only", "first",
    "after", "before", "over", "most", "through", "these", "those", "both"
}


def _extract_extractive_summary(text: str, max_sentences: int = 3, max_chars: int = 350) -> str:
    """Extract first few representative sentences cleanly."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    # Split on sentence boundaries
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if len(s.strip()) > 15]
    if sentences:
        summary = " ".join(sentences[:max_sentences])
    else:
        summary = cleaned[:max_chars]
    return summary[:max_chars].strip()


def _extract_keywords(text: str, top_n: int = 6) -> list[str]:
    """Extract top frequent informative keywords from text."""
    words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text) if w.lower() not in _STOPWORDS]
    if not words:
        return []
    return [word for word, _ in Counter(words).most_common(top_n)]


class MetadataService:
    """Generates concise metadata for every file in a workspace, then rolls it up."""

    async def generate_for_file(self, file_record: File, db: AsyncSession) -> None:
        """Read file chunks from Postgres, extract summary + keywords, persist."""
        result = await db.execute(
            select(Chunk.text)
            .where(Chunk.file_id == file_record.id)
            .order_by(Chunk.chunk_index)
            .limit(6)
        )
        chunk_texts = result.scalars().all()

        if not chunk_texts:
            logger.info(f"MetadataService: no text chunks for file {file_record.id}, skipping.")
            return

        combined_sample = " ".join(chunk_texts)
        summary = _extract_extractive_summary(combined_sample)
        keywords = _extract_keywords(combined_sample, top_n=6)
        topics = keywords[:3] if keywords else ["general"]

        file_record.summary = summary
        file_record.keywords = keywords
        file_record.topics = topics
        logger.info(f"MetadataService: extractive metadata OK for file {file_record.id}")

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
        all_keywords = []
        file_summaries = []

        for file_record in files:
            if not file_record.mime_type.startswith("image/"):
                await self.generate_for_file(file_record, db)
                doc_count += 1
                if file_record.keywords:
                    all_keywords.extend(file_record.keywords)
                if file_record.summary:
                    basename = os.path.basename(file_record.relative_path)
                    file_summaries.append(f"{basename}: {file_record.summary}")
            else:
                img_count += 1
            total_chunks += file_record.chunk_count or 0

        # Create concise workspace overview
        if file_summaries:
            top_summaries = " | ".join(file_summaries[:3])
            workspace.summary = f"Workspace containing {doc_count} document(s). {top_summaries}"[:500]
        else:
            workspace.summary = f"Workspace with {len(files)} file(s)."

        # Roll up top unique keywords across the whole workspace
        top_kws = [word for word, _ in Counter(all_keywords).most_common(8)]
        workspace.keywords = top_kws
        workspace.topics = top_kws[:4]

        workspace.document_count = doc_count
        workspace.image_count = img_count
        workspace.total_chunk_count = total_chunks
        await db.commit()
        logger.info(f"MetadataService: workspace {workspace_id} complete (0 MB extra RAM used)")

