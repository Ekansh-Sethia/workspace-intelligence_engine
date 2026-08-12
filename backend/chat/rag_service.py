"""
RAGService — Phase 11

Orchestrates the full Retrieval-Augmented Generation pipeline with three layers
of intelligent context expansion:

  Layer 0 — Conversational Query Rewriting
    Before searching, rewrites the user's question into a self-contained query
    using the chat history, so follow-up questions resolve correctly.

  Layer 1 — Sibling Chunk Expansion
    After the initial top-K retrieval, fetches the ±1 neighbouring chunks for
    each hit from Postgres. This captures context that is physically adjacent
    in the source document (e.g., an answer key on the next page, a conclusion
    paragraph, a sub-heading that precedes the matched text).

  Layer 2 — Agentic Multi-Hop RAG
    The LLM is given the initial context and a `search_workspace` tool.
    If it determines it needs more information, it calls the tool with a new
    targeted query. The loop is hard-capped at MAX_AGENT_ITERATIONS = 3,
    making infinite loops provably impossible.

Engineering guideline compliance
---------------------------------
- The Agentic loop uses a Python `for i in range(N)` — it cannot execute more
  than N times regardless of what the LLM returns.
- On any failure in the agentic or query-rewriting step, the code falls back
  gracefully to the simpler retrieval path — the user always gets an answer.
- All helper functions are kept under 40 lines; the main method is the
  orchestration layer only.
"""
import json
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_
from sqlalchemy.future import select

from chat.models import ChatSession, ChatMessage
from embeddings.search import SearchService
from embeddings import FastEmbedProvider
from llm.gateway import llm_chat_stream, llm_complete, _router
from utils.config import settings
from utils.logger import logger
from workspaces.models import Chunk, File
from workspaces.search_schemas import SearchResult


# ── Constants ──────────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS = 3  # Hard cap; loop is `for i in range(N)` — provably finite
MAX_CONTEXT_CHUNKS = 8    # Cap total context chunks to stay comfortably under Groq 6k TPM fallback limit


# ── Query Rewriter ─────────────────────────────────────────────────────────
_REWRITE_SYSTEM_PROMPT = """\
You are a search query rewriter for a document retrieval system.

Your ONLY job is to rewrite the user's latest message into a single, self-contained
search query that can be understood without any prior conversation context.

Rules:
- If the latest message is already self-contained and clear, return it unchanged.
- If the latest message is a follow-up (e.g. "what year is that?", "is B correct?",
  "where is that from?", "tell me more"), rewrite it by incorporating relevant
  context from the conversation history to make it a complete, standalone query.
- Output ONLY the rewritten query text. No explanation, no quotes, no extra text.
- Keep the rewritten query concise (under 120 words).
"""


async def _rewrite_query(query: str, history: list[dict]) -> str:
    """
    Use the LLM to rewrite a follow-up question into a self-contained search query.
    Falls back to the original query on any failure.
    """
    if not history:
        return query

    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" for msg in history[-6:]
    )
    user_message = (
        f"Conversation history:\n{history_text}\n\n"
        f"Latest user message: {query}\n\n"
        f"Rewritten standalone search query:"
    )

    try:
        rewritten = await llm_complete(
            system_prompt=_REWRITE_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=150,
        )
        logger.info(
            f"RAGService: query rewritten\n  Original : {query!r}\n  Rewritten: {rewritten!r}"
        )
        return rewritten
    except Exception as exc:
        logger.warning(f"RAGService: query rewriting failed ({exc}), using original query")
        return query


# ── Sibling Chunk Expansion ────────────────────────────────────────────────
async def _expand_with_siblings(
    chunks: list[SearchResult],
    db: AsyncSession,
) -> list[SearchResult]:
    """
    Layer 1: For each retrieved chunk, also fetch its immediate neighbours
    (chunk_index - 1 and chunk_index + 1) from the same file in Postgres.

    This costs one extra DB query but significantly improves context continuity,
    especially for documents where an answer, conclusion, or definition lives
    on the page immediately before or after the matched section.

    Returns a deduplicated, file-and-index sorted list of SearchResult objects.
    """
    if not chunks:
        return chunks

    # Build conditions for each hit's file+sibling range
    conditions = []
    for c in chunks:
        conditions.append(
            (Chunk.file_id == c.file_id) &
            (Chunk.chunk_index.in_([c.chunk_index - 1, c.chunk_index + 1]))
        )

    result = await db.execute(
        select(Chunk).where(or_(*conditions))
    )
    sibling_rows = result.scalars().all()

    # Convert Chunk ORM rows into SearchResult objects (score=0 marks them as context)
    existing_ids = {c.chunk_id for c in chunks}
    new_chunks = [
        SearchResult(
            score=0.0,  # siblings aren't ranked by similarity
            text=sib.text,
            file_id=sib.file_id,
            chunk_id=sib.id,
            chunk_index=sib.chunk_index,
            page_number=sib.page_number,
            chunk_type=getattr(sib, "chunk_type", "text"),
        )
        for sib in sibling_rows
        if sib.id not in existing_ids
    ]

    merged = chunks + new_chunks
    # Sort by file then position so the LLM sees coherent, ordered context
    merged.sort(key=lambda c: (c.file_id, c.chunk_index))

    logger.info(
        f"RAGService: sibling expansion added {len(new_chunks)} chunks "
        f"(total context: {len(merged)} chunks)"
    )
    return merged


async def _expand_with_answer_keys(
    chunks: list[SearchResult],
    db: AsyncSession,
) -> list[SearchResult]:
    """
    Layer 2.5: For any files retrieved in the search, explicitly fetch any chunks
    tagged as 'answer_key' in that file, regardless of semantic similarity.
    This guarantees that if the search matches a question, its answer key is pulled.
    """
    if not chunks:
        return chunks

    file_ids = list({c.file_id for c in chunks})
    
    result = await db.execute(
        select(Chunk).where(
            (Chunk.file_id.in_(file_ids)) &
            (Chunk.chunk_type == "answer_key")
        )
    )
    answer_key_rows = result.scalars().all()

    existing_ids = {c.chunk_id for c in chunks}
    new_chunks = [
        SearchResult(
            score=0.0,
            text=ak.text,
            file_id=ak.file_id,
            chunk_id=ak.id,
            chunk_index=ak.chunk_index,
            page_number=ak.page_number,
            chunk_type=getattr(ak, "chunk_type", "text"),
        )
        for ak in answer_key_rows
        if ak.id not in existing_ids
    ]

    merged = chunks + new_chunks
    merged.sort(key=lambda c: (c.file_id, c.chunk_index))

    logger.info(
        f"RAGService: answer key expansion added {len(new_chunks)} chunks "
        f"(total context: {len(merged)} chunks)"
    )
    return merged


# ── File Name Lookup ───────────────────────────────────────────────────────
async def _fetch_file_names(file_ids: list[int], db: AsyncSession) -> dict[int, str]:
    """
    Fetch the relative_path for each file_id from Postgres.
    Returns {file_id: basename}. Uses a single IN query.
    """
    if not file_ids:
        return {}
    result = await db.execute(
        select(File.id, File.relative_path).where(File.id.in_(file_ids))
    )
    return {row.id: os.path.basename(row.relative_path) for row in result.all()}


# ── System Prompt Builder ──────────────────────────────────────────────────
_SYSTEM_PROMPT_TEMPLATE = """\
You are a precise, helpful AI assistant for the Workspace Intelligence Engine.

You are answering questions about a specific workspace. You have been given a set
of relevant document excerpts (context chunks) retrieved from that workspace.
Each chunk is labelled with the source filename and its structural type.

STRICT RULES:
1. Only use information from the provided context chunks to answer.
2. STRICT GROUNDING: You MUST NOT use your internal knowledge to answer the question.
   If the provided context chunks do not contain the exact answer for the user's question,
   you must reply: "The provided context does not contain the answer to this question."
   Do not attempt to guess or calculate the answer yourself.
3. Never make up facts, URLs, code, or names that are not present in the context.
4. Be concise and clear. Format your response as plain text with clear spacing and
   bullet points. Do NOT use markdown bold (**text**) or headers.
5. When you reference information, you MAY mention the source filename naturally
   (e.g. "According to notes.pdf, ..."). Do not cite chunk numbers.
6. CRITICAL: The context may contain multiple different questions or completely
   unrelated topics. DO NOT mix options, answers, or text from different questions.
   If the user asks about a specific question, isolate that specific question and
   ignore all others.

QUIZ GRADING EXCEPTION:
If the user is submitting answers to a quiz that was generated earlier in the chat
history, you MUST act as a teacher and grade their answers. To do this:
- Read the quiz questions and the Answer Key from the chat history.
- Compare the user's answers to the Answer Key.
- Tell the user which of their answers are correct and which are wrong, and briefly
  explain the correct answer for any they got wrong using the explanations in the Answer Key.
- You do NOT need to rely on the context chunks for grading, because the correct answers are already in the chat history.

CONTEXT CHUNKS:
{context}
"""

# Tool definition for agentic search — LiteLLM/OpenAI function calling format
_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_workspace",
        "description": (
            "Search the workspace documents for additional information. "
            "Use this when the current context is insufficient to answer the question. "
            "Be specific and targeted in your query for best results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A specific, targeted search query to find the missing information.",
                }
            },
            "required": ["query"],
        },
    },
}


def _format_chunks(chunks: list[SearchResult], file_names: dict[int, str]) -> str:
    """Format chunks into a readable context string for the system prompt."""
    return "\n\n".join(
        (
            f"[Source: {file_names.get(c.file_id, f'file_id={c.file_id}')} "
            f"| type: {c.chunk_type}"
            f"{f' | page={c.page_number}' if c.page_number else ''}]\n{c.text}"
        )
        for c in chunks
    )


def _build_system_prompt(chunks: list[SearchResult], file_names: dict[int, str]) -> str:
    """Build the grounded system prompt with filename-annotated context chunks."""
    if not chunks:
        return (
            "You are a helpful AI assistant. The semantic search returned no relevant "
            "context for this query. Inform the user politely that you could not find "
            "relevant information in this workspace for their question."
        )
        
    # We must enforce MAX_CONTEXT_CHUNKS to prevent token explosion for fallback models.
    # Prioritize answer keys (vital for grading), then highest-scoring semantic hits.
    answer_keys = [c for c in chunks if c.chunk_type == "answer_key"]
    others = [c for c in chunks if c.chunk_type != "answer_key"]
    
    # Sort others by score descending (siblings and agentic hits might have score=0, 
    # but initial hits have real cosine scores).
    others.sort(key=lambda c: c.score, reverse=True)
    
    capped_chunks = (answer_keys + others)[:MAX_CONTEXT_CHUNKS]
    
    # Re-sort capped chunks sequentially by file and index to maintain reading flow
    capped_chunks.sort(key=lambda c: (c.file_id, c.chunk_index))

    return _SYSTEM_PROMPT_TEMPLATE.format(context=_format_chunks(capped_chunks, file_names))


def _build_history_messages(session_messages: list[ChatMessage]) -> list[dict]:
    """Convert the last N Postgres ChatMessage rows to the OpenAI message format."""
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

    def _search(self, workspace_id: int, query: str, limit: int | None = None) -> list[SearchResult]:
        """Thin wrapper around SearchService for use inside the agentic loop."""
        return self._search_service.search(
            workspace_id=workspace_id,
            query=query,
            limit=limit or 3,  # Hard limit to 3 to prevent token explosion during expansion
        )

    async def stream_answer(
        self,
        workspace_id: int,
        session_id: int,
        query: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute one RAG turn and yield SSE-formatted token chunks.

        Flow:
          load history
          → rewrite query (Layer 0)
          → initial retrieval
          → sibling expansion (Layer 1)
          → agentic multi-hop loop (Layer 2, up to MAX_AGENT_ITERATIONS)
          → stream final LLM response
          → persist + cite

        Yields:
            SSE strings:  data: <token>\\n\\n
                          data: [SOURCES]<json>\\n\\n
                          data: [DONE]\\n\\n
        """
        # 1. Load conversation history (needed for query rewriting)
        history_result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        history_messages = _build_history_messages(history_result.scalars().all())

        # 2. Layer 0 — Conversational Query Rewriting
        search_query = await _rewrite_query(query, history_messages)

        # 3. Initial retrieval pass (capped at 3 hits)
        chunks: list[SearchResult] = self._search(workspace_id, search_query, limit=3)
        logger.info(
            f"RAGService: initial retrieval — {len(chunks)} chunks "
            f"for workspace={workspace_id}, session={session_id}"
        )

        # 4. Layer 1 — Sibling chunk expansion
        chunks = await _expand_with_siblings(chunks, self._db)

        # 4.5 Layer 2.5 — Auto-fetch Answer Keys for matched files
        chunks = await _expand_with_answer_keys(chunks, self._db)

        # 5. Enrich with filenames (single IN query)
        unique_file_ids = list({c.file_id for c in chunks})
        file_names = await _fetch_file_names(unique_file_ids, self._db)

        # 6. Layer 2 — Agentic multi-hop loop
        #    The LLM can call `search_workspace` up to MAX_AGENT_ITERATIONS times.
        #    The `for` loop is provably finite — cannot exceed MAX_AGENT_ITERATIONS.
        all_chunk_ids = {c.chunk_id for c in chunks}
        tool_messages: list[dict] = []  # tracks tool calls within this turn

        for iteration in range(MAX_AGENT_ITERATIONS):
            system_prompt = _build_system_prompt(chunks, file_names)
            context_message = (
                f"[Context updated after search #{iteration}]" if iteration > 0
                else None
            )
            messages_for_agent = history_messages.copy()
            messages_for_agent.append({"role": "user", "content": query})
            messages_for_agent.extend(tool_messages)
            if context_message:
                messages_for_agent.append({"role": "system", "content": context_message})

            try:
                agent_response = await _router.acompletion(
                    model="primary",
                    messages=[{"role": "system", "content": system_prompt}] + messages_for_agent,
                    tools=[_SEARCH_TOOL],
                    tool_choice="auto",
                    stream=False,
                    max_tokens=512,
                )

                choice = agent_response.choices[0]

                # If the LLM didn't call any tools, it's satisfied — break early
                if not (choice.finish_reason == "tool_calls" and choice.message.tool_calls):
                    logger.info(f"RAGService: agent satisfied after {iteration} extra search(es)")
                    break

                # Process each tool call the LLM issued
                for tc in choice.message.tool_calls:
                    if tc.function.name != "search_workspace":
                        continue
                    args = json.loads(tc.function.arguments)
                    tool_query = args.get("query", "")
                    if not tool_query:
                        continue

                    logger.info(f"RAGService: agent search #{iteration + 1} — {tool_query!r}")
                    new_chunks = self._search(workspace_id, tool_query, limit=3)
                    # Expand new hits with their siblings too
                    new_chunks = await _expand_with_siblings(new_chunks, self._db)
                    new_chunks = await _expand_with_answer_keys(new_chunks, self._db)

                    # Merge deduplicated results into the growing context
                    for nc in new_chunks:
                        if nc.chunk_id not in all_chunk_ids:
                            chunks.append(nc)
                            all_chunk_ids.add(nc.chunk_id)

                    # Re-fetch filenames for any new files
                    new_file_ids = [nc.file_id for nc in new_chunks if nc.file_id not in file_names]
                    if new_file_ids:
                        file_names.update(await _fetch_file_names(new_file_ids, self._db))

                    chunks.sort(key=lambda c: (c.file_id, c.chunk_index))

                    # Record tool call + result for the next iteration's message list
                    tool_messages.append({
                        "role": "assistant",
                        "tool_calls": [tc.model_dump()],
                        "content": None,
                    })
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Search completed. Found {len(new_chunks)} relevant chunks. The system prompt context has been updated automatically." if new_chunks else "No relevant results found.",
                    })

            except Exception as exc:
                logger.warning(f"RAGService: agentic iteration {iteration} failed ({exc}), proceeding with current context")
                break

        # 7. Persist user message
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content=query,
            sources=[],
        )
        self._db.add(user_message)
        await self._db.commit()

        # 8. Auto-set session title on first message
        session_result = await self._db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = session_result.scalars().first()
        if session and session.title == "New Chat":
            session.title = _auto_title(query)
            await self._db.commit()

        # 9. Build final system prompt with all accumulated context
        final_system_prompt = _build_system_prompt(chunks, file_names)
        final_messages = history_messages + [{"role": "user", "content": query}]

        # 10. Stream the final LLM response
        full_response_text = ""
        try:
            stream = await llm_chat_stream(
                system_prompt=final_system_prompt,
                messages=final_messages,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_response_text += delta
                    yield f"data: {json.dumps(delta)}\n\n"
        except Exception as exc:
            logger.error(f"RAGService: LLM streaming error: {exc}")
            error_text = "I'm sorry, I encountered an error while generating a response. Please try again."
            full_response_text = error_text
            yield f"data: {json.dumps(error_text)}\n\n"

        # 11. Persist complete assistant message with all source chunk IDs
        source_ids = list(all_chunk_ids)
        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=full_response_text,
            sources=source_ids,
        )
        self._db.add(assistant_message)
        await self._db.commit()
        await self._db.refresh(assistant_message)

        # 12. Send citations and done event
        yield f"data: [SOURCES]{json.dumps(source_ids)}\n\n"
        yield "data: [DONE]\n\n"

        logger.info(
            f"RAGService: completed turn for session={session_id}, "
            f"tokens≈{len(full_response_text.split())}, sources={source_ids}"
        )
