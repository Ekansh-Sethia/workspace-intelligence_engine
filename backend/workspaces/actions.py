"""
ActionService - Phase 13

Provides workspace-level actions beyond simple Q&A:

  export_workspace -- Merge all file chunks into a single downloadable TXT/Markdown.
  generate_quiz    -- Generate MCQ quiz questions from a file or workspace.
  generate_notes   -- Generate structured revision notes from a file or workspace.

Design decisions:
- All text is read from Postgres chunks (clean, parsed, deduplicated).
- Quiz and notes use llm_complete (non-streaming) then stream result back.
- Export is purely deterministic (no LLM call needed).
"""
import os
import json
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from workspaces.models import File, Chunk
from llm.gateway import llm_complete, llm_stream
from utils.logger import logger


_QUIZ_SYSTEM = (
    "You are an expert quiz generator. You will receive text from a study document. "
    "Generate exactly 5 multiple-choice questions based on this text. "
    "Format each question exactly like this:\n"
    "Q1. [Question text]\n"
    "(A) [Option A]\n(B) [Option B]\n(C) [Option C]\n(D) [Option D]\n\n"
    "Generate all 5 questions in this format. Do NOT provide the correct answers. "
    "Do not add any other text or explanation."
)

_NOTES_SYSTEM = (
    "You are an expert study notes generator. You will receive text from a document. "
    "Produce concise, well-structured revision notes with: "
    "a Topic heading, Key Concepts (bullet list), Important Definitions (term: definition), "
    "and Key Takeaways (numbered list). "
    "Be precise and educational. Cover all important points from the provided text."
)


async def _fetch_file_chunks(file_id: int, db: AsyncSession, limit: int = 20) -> list[str]:
    """Fetch up to `limit` chunks for a file, ordered by position."""
    result = await db.execute(
        select(Chunk.text)
        .where(Chunk.file_id == file_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
    )
    return result.scalars().all()


async def _fetch_workspace_chunks(workspace_id: int, db: AsyncSession) -> list[tuple[str, str]]:
    """
    Fetch all chunks for a workspace with their source filename.
    Returns list of (filename, chunk_text) tuples.
    """
    result = await db.execute(
        select(File.relative_path, Chunk.text, Chunk.chunk_index)
        .join(Chunk, Chunk.file_id == File.id)
        .where(File.workspace_id == workspace_id)
        .order_by(File.relative_path, Chunk.chunk_index)
    )
    return [(os.path.basename(row.relative_path), row.text) for row in result.all()]


class ActionService:
    """
    Executes workspace-level actions.
    Each method is an async generator yielding SSE-formatted strings.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def export_workspace(self, workspace_id: int, format: str = "txt") -> str:
        """
        Merge all workspace chunks into a single text blob.
        Returns the merged content as a plain string (non-streaming).
        """
        chunks = await _fetch_workspace_chunks(workspace_id, self._db)

        sections = []
        current_file = None
        for filename, text in chunks:
            if filename != current_file:
                if format == "md":
                    sections.append(f"\n\n## {filename}\n")
                else:
                    sections.append(f"\n\n{'='*60}\n{filename}\n{'='*60}\n")
                current_file = filename
            sections.append(text)
        return "\n".join(sections).strip()

    async def generate_quiz(
        self,
        workspace_id: int,
        file_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Generate a 5-question MCQ quiz from a specific file or the workspace."""
        if file_id:
            file_result = await self._db.execute(
                select(File).where(File.id == file_id, File.workspace_id == workspace_id)
            )
            file_record = file_result.scalars().first()
            if not file_record:
                yield f"data: {json.dumps('Error: File not found in this workspace.')}\n\n"
                yield "data: [DONE]\n\n"
                return
            chunk_texts = await _fetch_file_chunks(file_id, self._db, limit=15)
            source_name = os.path.basename(file_record.relative_path)
        else:
            all_chunks = await _fetch_workspace_chunks(workspace_id, self._db)
            chunk_texts = [text for _, text in all_chunks[:20]]
            source_name = "the workspace"

        if not chunk_texts:
            yield f"data: {json.dumps('No content found to generate a quiz from.')}\n\n"
            yield "data: [DONE]\n\n"
            return

        combined_text = "\n\n".join(chunk_texts)[:5000]
        logger.info(f"ActionService: generating quiz from {source_name}")

        try:
            response_str = f"Quiz generated from {source_name}:\n\n"
            yield f"data: {json.dumps(response_str)}\n\n"
            
            async for token in llm_stream(
                system_prompt=_QUIZ_SYSTEM,
                user_message=f"Generate a quiz from this text:\n\n{combined_text}",
                max_tokens=2500,
            ):
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as exc:
            logger.warning(f"ActionService: quiz generation failed: {exc!r}")
            yield f"data: {json.dumps('Failed to generate quiz. Please try again.')}\n\n"

        yield "data: [SOURCES][]\n\n"
        yield "data: [DONE]\n\n"

    async def generate_notes(
        self,
        workspace_id: int,
        file_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Generate structured revision notes from a file or the whole workspace."""
        if file_id:
            file_result = await self._db.execute(
                select(File).where(File.id == file_id, File.workspace_id == workspace_id)
            )
            file_record = file_result.scalars().first()
            if not file_record:
                yield f"data: {json.dumps('Error: File not found in this workspace.')}\n\n"
                yield "data: [DONE]\n\n"
                return
            chunk_texts = await _fetch_file_chunks(file_id, self._db, limit=20)
            source_name = os.path.basename(file_record.relative_path)
        else:
            all_chunks = await _fetch_workspace_chunks(workspace_id, self._db)
            chunk_texts = [text for _, text in all_chunks[:25]]
            source_name = "the workspace"

        if not chunk_texts:
            yield f"data: {json.dumps('No content found to generate notes from.')}\n\n"
            yield "data: [DONE]\n\n"
            return

        combined_text = "\n\n".join(chunk_texts)[:6000]
        logger.info(f"ActionService: generating notes from {source_name}")

        try:
            response_str = f"Revision Notes for {source_name}:\n\n"
            yield f"data: {json.dumps(response_str)}\n\n"
            
            async for token in llm_stream(
                system_prompt=_NOTES_SYSTEM,
                user_message=f"Generate revision notes from this text:\n\n{combined_text}",
                max_tokens=2500,
            ):
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as exc:
            logger.warning(f"ActionService: notes generation failed: {exc!r}")
            yield f"data: {json.dumps('Failed to generate notes. Please try again.')}\n\n"

        yield "data: [SOURCES][]\n\n"
        yield "data: [DONE]\n\n"
