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

from core.database import get_db
from authentication.dependencies import get_current_user
from authentication.models import User
from workspaces.models import Workspace
from chat.models import ChatSession, ChatMessage
from chat.schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageResponse,
    ChatRequest,
    SessionHistoryResponse,
)
from chat.rag_service import RAGService

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

    The response is a text/event-stream with the following event types:
      data: <token>           — incremental LLM token
      data: [SOURCES][...]    — JSON array of chunk_ids used to ground the answer
      data: [DONE]            — signals end of stream
    """
    await _get_owned_ready_workspace(workspace_id, db, current_user)
    await _get_owned_session(session_id, workspace_id, db)

    rag_service = RAGService(db=db)

    return StreamingResponse(
        rag_service.stream_answer(
            workspace_id=workspace_id,
            session_id=session_id,
            query=body.query,
        ),
        media_type="text/event-stream",
        headers={
            # Prevent proxy buffering so tokens reach the client immediately
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
