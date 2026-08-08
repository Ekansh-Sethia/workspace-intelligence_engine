"""
RAGService — Phase 9

Orchestrates the full Retrieval-Augmented Generation pipeline:

  1. Retrieve:  Call SearchService to get the top-K relevant chunks from Qdrant.
  2. Build:     Construct a grounded system prompt with those chunks as context.
  3. Generate:  Stream the LLM response token-by-token via the LLM Gateway.
  4. Persist:   Save both the user message and assembled assistant message to Postgres.
  5. Cite:      Return the source chunk_ids alongside the streamed response.

Engineering guideline compliance
---------------------------------
- The LLM is the final step, as required by engineering_guidelines.md.
- The system prompt strictly grounds the LLM in the retrieved context to
  prevent hallucination. If no relevant chunks are found, the LLM is
  instructed to say so explicitly rather than making up an answer.
- Function size is kept under 40 lines by extracting helpers (_build_system_prompt,
  _build_history_messages, _auto_title).
"""
import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from chat.models import ChatSession, ChatMessage
from embeddings.search import SearchService
from embeddings import FastEmbedProvider
from llm.gateway import llm_chat_stream
from utils.config import settings
from utils.logger import logger
from workspaces.search_schemas import SearchResult


_SYSTEM_PROMPT_TEMPLATE = """You are a precise, helpful AI assistant for the Workspace Intelligence Engine.

You are answering questions about a specific workspace. You have been given a set of relevant document excerpts (context chunks) retrieved from that workspace.

STRICT RULES:
1. Only use information from the provided context chunks to answer.
2. If the context chunks are completely unrelated to the question, politely inform the user that the workspace doesn't contain the answer. However, if the chunks contain partial or related information, answer to the best of your ability without adding disclaimers about lacking information.
3. Never make up facts, URLs, code, or names that are not present in the context.
4. Be concise and clear. DO NOT use markdown formatting (like ** for bold). Format your response as plain text with clear spacing and bullet points.

CONTEXT CHUNKS:
{context}
"""


def _build_system_prompt(chunks: list[SearchResult]) -> str:
    """Format retrieved chunks into the grounding system prompt."""
    if not chunks:
        return (
            "You are a helpful AI assistant. The semantic search returned no relevant "
            "context for this query. Inform the user politely that you could not find "
            "relevant information in this workspace for their question."
        )

    formatted_chunks = "\n\n".join(
        f"[Chunk {i + 1} | file_id={c.file_id} | chunk_index={c.chunk_index}"
        f"{f' | page={c.page_number}' if c.page_number else ''}]\n{c.text}"
        for i, c in enumerate(chunks)
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(context=formatted_chunks)


def _build_history_messages(session_messages: list[ChatMessage]) -> list[dict]:
    """
    Convert the last N turns of Postgres ChatMessage rows into the
    OpenAI-compatible message list format that LiteLLM expects.
    """
    recent = session_messages[-(settings.RAG_HISTORY_TURNS):]
    return [{"role": msg.role, "content": msg.content} for msg in recent]


def _auto_title(query: str, max_length: int = 60) -> str:
    """Generate a session title from the first user query."""
    title = query.strip().replace("\n", " ")
    return title[:max_length] + ("…" if len(title) > max_length else "")


class RAGService:
    """
    Orchestrates retrieval + generation for a single chat turn.

    Args:
        db: Async SQLAlchemy session (injected via FastAPI Depends).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._search_service = SearchService(provider=FastEmbedProvider())

    async def stream_answer(
        self,
        workspace_id: int,
        session_id: int,
        query: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute one RAG turn and yield SSE-formatted token chunks.

        Flow:
          retrieve → build prompt → load history → stream LLM → persist → yield done event

        Yields:
            Server-Sent Event strings in the format:
              data: <token>\\n\\n
              data: [SOURCES]<json>\\n\\n
              data: [DONE]\\n\\n
        """
        # 1. Retrieve top-K relevant chunks
        chunks: list[SearchResult] = self._search_service.search(
            workspace_id=workspace_id,
            query=query,
            limit=settings.RAG_TOP_K,
        )
        logger.info(
            f"RAGService: retrieved {len(chunks)} chunks for "
            f"workspace={workspace_id}, session={session_id}"
        )

        # 2. Build grounded system prompt
        system_prompt = _build_system_prompt(chunks)

        # 3. Load recent conversation history
        history_result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        history_messages = _build_history_messages(history_result.scalars().all())

        # 4. Persist the user's message immediately
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content=query,
            sources=[],
        )
        self._db.add(user_message)
        await self._db.commit()

        # 5. Auto-set the session title on first message
        session_result = await self._db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = session_result.scalars().first()
        if session and session.title == "New Chat":
            session.title = _auto_title(query)
            await self._db.commit()

        # 6. Append the current user query to the messages list for the LLM
        history_messages.append({"role": "user", "content": query})

        # 7. Stream the LLM response
        full_response_text = ""
        try:
            stream = await llm_chat_stream(
                system_prompt=system_prompt,
                messages=history_messages,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_response_text += delta
                    # Yield each token as a JSON-encoded SSE data event to preserve newlines
                    yield f"data: {json.dumps(delta)}\n\n"
        except Exception as exc:
            logger.error(f"RAGService: LLM streaming error: {exc}")
            error_text = "I'm sorry, I encountered an error while generating a response. Please try again."
            full_response_text = error_text
            yield f"data: {error_text}\n\n"

        # 8. Persist the complete assistant message with source chunk_ids
        source_ids = [c.chunk_id for c in chunks]
        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=full_response_text,
            sources=source_ids,
        )
        self._db.add(assistant_message)
        await self._db.commit()
        await self._db.refresh(assistant_message)

        # 9. Send sources as a final SSE event so the frontend can render citations
        yield f"data: [SOURCES]{json.dumps(source_ids)}\n\n"
        yield "data: [DONE]\n\n"

        logger.info(
            f"RAGService: completed turn for session={session_id}, "
            f"tokens≈{len(full_response_text.split())}, sources={source_ids}"
        )
