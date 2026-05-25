"""Session management API — persistent chat conversations."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, async_session
from app.models import (
    Agent, Session, Message, Task, TaskStatus, TaskStrategy,
    OperationalStatus, ToolCallRecord,
)
from app.schemas import SessionCreate, SessionResponse, MessageCreate, MessageResponse
from app.services.orchestrator import execute_task
from app.services.logger import log_broadcaster

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_background_tasks: set[asyncio.Task] = set()


# ---------- CRUD ----------

@router.post("", response_model=SessionResponse)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = Session(
        title=body.title or "New Chat",
        strategy=body.strategy,
        agent_ids=body.agent_ids,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return await _load_session(db, session.id)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.messages).selectinload(Message.tool_calls))
        .order_by(Session.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    return await _load_session(db, session_id)


@router.delete("/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    sess = await db.get(Session, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    await db.delete(sess)
    await db.commit()
    return {"deleted": True}


# ---------- Messages ----------

@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .options(selectinload(Message.tool_calls))
        .order_by(Message.id)
    )
    return result.scalars().all()


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Send a user message and stream back the assistant response via SSE."""
    sess = await db.get(Session, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    # Persist user message
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)

    # Auto-title from first message
    if sess.title == "New Chat" or not sess.title:
        sess.title = body.content[:60].strip()

    # Update session timestamp
    sess.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user_msg)

    # Build conversation history from past messages
    past_messages = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.id != user_msg.id)
        .order_by(Message.id)
    )
    history = []
    for m in past_messages.scalars().all():
        role = "user" if m.role == "user" else "assistant"
        content = m.content
        if m.structured and role == "assistant":
            content = m.structured.get("final_answer", m.content)
        history.append({"role": role, "content": content})

    # Create a placeholder assistant message
    assistant_msg = Message(
        session_id=session_id,
        role="assistant",
        content="",
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    async def event_generator():
        # Subscribe to log events for streaming
        queue = await log_broadcaster.subscribe(task_id=None)
        task_id_holder = []

        async def run_in_bg():
            async with async_session() as bg_session:
                try:
                    # Get agents
                    agent_ids = sess.agent_ids
                    if agent_ids:
                        result = await bg_session.execute(
                            select(Agent).where(
                                Agent.id.in_(agent_ids),
                                Agent.is_active == True,
                                Agent.operational_status == OperationalStatus.ACTIVE,
                            )
                        )
                    else:
                        result = await bg_session.execute(
                            select(Agent).where(
                                Agent.is_active == True,
                                Agent.operational_status == OperationalStatus.ACTIVE,
                            )
                        )
                    agents = list(result.scalars().all())

                    if not agents:
                        async with async_session() as s2:
                            msg = await s2.get(Message, assistant_msg.id)
                            if msg:
                                msg.content = "No active agents available."
                                msg.structured = {"final_answer": "No active agents available.", "tool_calls": [], "agent_steps": []}
                                await s2.commit()
                        return

                    # Create task
                    task = Task(
                        session_id=session_id,
                        prompt=body.content,
                        strategy=sess.strategy,
                        status=TaskStatus.PENDING,
                    )
                    bg_session.add(task)
                    await bg_session.flush()
                    task_id_holder.append(task.id)

                    settings = get_settings()
                    workspace_dir = os.path.join(settings.workspace_base_dir, f"session_{session_id}")

                    await execute_task(
                        bg_session,
                        task,
                        agents,
                        conversation_history=history,
                        workspace_dir=workspace_dir,
                    )
                    await bg_session.commit()

                    # Update assistant message with results
                    structured = task.task_metadata or {}
                    final_answer = task.final_output or ""

                    async with async_session() as s2:
                        msg = await s2.get(Message, assistant_msg.id)
                        if msg:
                            msg.content = final_answer
                            msg.structured = structured
                            msg.task_id = task.id

                            # Persist tool call records
                            for tc in structured.get("tool_calls", []):
                                record = ToolCallRecord(
                                    message_id=assistant_msg.id,
                                    tool_name=tc.get("tool_name", ""),
                                    agent_name=tc.get("agent_name", ""),
                                    input_args=tc.get("input_args"),
                                    output=tc.get("output"),
                                    duration_ms=tc.get("duration_ms"),
                                    status=tc.get("status", "success"),
                                )
                                s2.add(record)

                            # Update session timestamp
                            session_obj = await s2.get(Session, session_id)
                            if session_obj:
                                session_obj.updated_at = datetime.now(timezone.utc)

                            await s2.commit()

                except Exception as e:
                    async with async_session() as s2:
                        msg = await s2.get(Message, assistant_msg.id)
                        if msg:
                            msg.content = f"Error: {str(e)}"
                            msg.structured = {"final_answer": f"Error: {str(e)}", "tool_calls": [], "agent_steps": []}
                            await s2.commit()

        bg = asyncio.create_task(run_in_bg())
        _background_tasks.add(bg)
        bg.add_done_callback(_background_tasks.discard)

        # Stream log events while task runs
        try:
            while not bg.done():
                try:
                    log_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {json.dumps({'type': 'log', 'data': log_msg})}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

            await bg

        finally:
            log_broadcaster.unsubscribe(queue)

        # Send final message with full structured output
        async with async_session() as s2:
            msg = await s2.get(Message, assistant_msg.id)
            if msg:
                resp = {
                    "id": msg.id,
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "structured": msg.structured,
                    "task_id": msg.task_id,
                    "created_at": msg.created_at.isoformat(),
                }
                yield f"data: {json.dumps({'type': 'done', 'message': resp})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------- Files ----------

@router.get("/{session_id}/files")
async def list_session_files(session_id: int):
    settings = get_settings()
    workspace = Path(settings.workspace_base_dir) / f"session_{session_id}"
    if not workspace.exists():
        return []
    return [f.name for f in workspace.iterdir() if f.is_file() and not f.name.endswith(".py")]


@router.get("/{session_id}/files/{filename}")
async def download_session_file(session_id: int, filename: str):
    settings = get_settings()
    workspace = Path(settings.workspace_base_dir) / f"session_{session_id}"
    target = (workspace / filename).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(400, "Invalid path")
    if not target.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(target), filename=filename)


# ---------- Helpers ----------

async def _load_session(db: AsyncSession, session_id: int) -> Session:
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .options(
            selectinload(Session.messages).selectinload(Message.tool_calls)
        )
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "Session not found")
    return sess
