"""
Chat Layer Router — Phase 9

Endpoints:
  POST   /workspaces/{id}/chat/sessions               Create a new chat session
  GET    /workspaces/{id}/chat/sessions               List sessions for a workspace
  GET    /workspaces/{id}/chat/sessions/{sid}         Get session history
  POST   /workspaces/{id}/chat/sessions/{sid}/messages Send a message (streaming SSE)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import json

from core.database import get_db
from authentication.dependencies import get_current_user
from authentication.models import User
from workspaces.models import Workspace, File
from chat.models import ChatSession, ChatMessage
from chat.schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageResponse,
    ChatRequest,
    SessionHistoryResponse,
)
from chat.rag_service import RAGService
from chat.intent_router import classify_intent, Intent
from workspaces.actions import ActionService
import re

router = APIRouter(prefix="/workspaces", tags=["Chat"])


async def _get_owned_ready_workspace(
    workspace_id: int,
    db: AsyncSession,
    current_user: User,
) -> Workspace:
    """Shared guard: verify ownership and READY status before any chat operation."""
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == current_user.id,
        )
    )
    workspace = result.scalars().first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Workspace is not ready for chat (current status: {workspace.status})",
        )
    return workspace


async def _get_owned_session(
    session_id: int,
    workspace_id: int,
    db: AsyncSession,
) -> ChatSession:
    """Verify the session belongs to the given workspace."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
        )
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post(
    "/{workspace_id}/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    workspace_id: int,
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    """Create a new chat session for this workspace."""
    await _get_owned_ready_workspace(workspace_id, db, current_user)

    session = ChatSession(
        workspace_id=workspace_id,
        user_id=current_user.id,
        title=body.title or "New Chat",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get(
    "/{workspace_id}/chat/sessions",
    response_model=list[ChatSessionResponse],
)
async def list_sessions(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSession]:
    """List all chat sessions for a workspace, newest first."""
    await _get_owned_ready_workspace(workspace_id, db, current_user)

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.workspace_id == workspace_id, ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{workspace_id}/chat/sessions/{session_id}",
    response_model=SessionHistoryResponse,
)
async def get_session_history(
    workspace_id: int,
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Retrieve the full message history for a session."""
    await _get_owned_ready_workspace(workspace_id, db, current_user)
    session = await _get_owned_session(session_id, workspace_id, db)

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = messages_result.scalars().all()

    return {"session": session, "messages": messages}


@router.delete(
    "/{workspace_id}/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    workspace_id: int,
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat session and all its messages."""
    await _get_owned_ready_workspace(workspace_id, db, current_user)
    session = await _get_owned_session(session_id, workspace_id, db)

    await db.delete(session)
    await db.commit()
    return None


@router.post(
    "/{workspace_id}/chat/sessions/{session_id}/messages",
    response_class=StreamingResponse,
)
async def send_message(
    workspace_id: int,
    session_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Send a user message and receive a streaming SSE response.

    Phase 9: Every request passes through the Intent Router first.

    The response is a text/event-stream with the following event types:
      data: <token>           — incremental LLM token
      data: [SOURCES][...]    — JSON array of chunk_ids used to ground the answer
      data: [DONE]            — signals end of stream
    """
    await _get_owned_ready_workspace(workspace_id, db, current_user)
    await _get_owned_session(session_id, workspace_id, db)

    # ── Phase 9: Intent Classification ────────────────────────────────────
    # Classify intent dynamically via Groq JSON
    intent_result = await classify_intent(body.query)
    intent = intent_result.intent
    # ── METADATA_SEARCH: serve directly from Postgres, zero LLM calls ────
    if intent == Intent.METADATA_SEARCH:
        stmt = select(File).where(File.workspace_id == workspace_id)
        
        if intent_result.file_type_filter:
            if intent_result.file_type_filter.startswith("image/"):
                stmt = stmt.where(File.mime_type.like("image/%"))
            else:
                stmt = stmt.where(File.mime_type == intent_result.file_type_filter)
            
        files_result = await db.execute(stmt)
        files = files_result.scalars().all()
        file_list = [
            f"{i+1}. {f.relative_path} ({f.mime_type}, {f.size:,} bytes)"
            for i, f in enumerate(files)
        ]
        response_text = (
            f"This workspace contains {len(files)} file(s):\n\n"
            + "\n".join(file_list)
        ) if files else "No files found in this workspace."

        async def _metadata_stream():
            yield f"data: {json.dumps(response_text)}\n\n"
            yield "data: [SOURCES][]\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _metadata_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── SUMMARIZATION: serve from pre-generated Phase 8 metadata ─────────
    if intent == Intent.SUMMARIZATION:
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = ws_result.scalars().first()
        summary = workspace.summary if workspace else None
        topics = workspace.topics or [] if workspace else []

        if summary:
            response_text = (
                f"Workspace Summary:\n\n{summary}\n\n"
                f"Topics: {', '.join(topics)}" if topics else f"Workspace Summary:\n\n{summary}"
            )
        else:
            response_text = (
                "The workspace summary has not been generated yet. "
                "Please wait for indexing to complete, or ask a specific question about your documents."
            )

        async def _summary_stream():
            yield f"data: {json.dumps(response_text)}\n\n"
            yield "data: [SOURCES][]\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _summary_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── ACTION: stateful action routing (Phase 13 updated) ───────────────
    if intent == Intent.ACTION:
        action_service = ActionService(db=db)
        
        # Route directly using the LLM-extracted parameter
        action_type = intent_result.action_type
        if action_type == "quiz":
            action_gen = action_service.generate_quiz(workspace_id=workspace_id)
        elif action_type == "notes":
            action_gen = action_service.generate_notes(workspace_id=workspace_id)
        else:
            action_gen = action_service.generate_notes(workspace_id=workspace_id)

        async def _stateful_action_stream():
            full_response = ""
            # Save user message immediately
            user_msg = ChatMessage(
                session_id=session_id,
                role="user",
                content=body.query,
                sources=[],
            )
            db.add(user_msg)
            await db.commit()

            async for chunk in action_gen:
                yield chunk
                # Extract the text from the SSE "data: ..." format to save to DB
                if chunk.startswith("data: ") and not chunk.startswith("data: [SOURCES]") and not chunk.startswith("data: [DONE]"):
                    text = chunk[6:].strip()
                    if text:
                        try:
                            import json
                            parsed_text = json.loads(text)
                            full_response += parsed_text + "\n"
                        except Exception:
                            full_response += text + "\n"

            # Save assistant message at the end
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=full_response.strip(),
                sources=[],
            )
            db.add(assistant_msg)
            await db.commit()

        return StreamingResponse(
            _stateful_action_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── SEMANTIC_SEARCH (default): full RAG pipeline ──────────────────────
    rag_service = RAGService(db=db)

    return StreamingResponse(
        rag_service.stream_answer(
            workspace_id=workspace_id,
            session_id=session_id,
            query=body.query,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
