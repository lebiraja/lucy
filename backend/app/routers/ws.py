"""WebSocket endpoint for real-time log streaming."""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.logger import log_broadcaster

router = APIRouter(tags=["websocket"])


@router.websocket("/api/ws/logs")
async def websocket_global_logs(websocket: WebSocket):
    """Stream all logs globally via WebSocket."""
    await websocket.accept()
    queue = log_broadcaster.subscribe()

    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        log_broadcaster.unsubscribe(queue)


@router.websocket("/api/ws/logs/{task_id}")
async def websocket_task_logs(websocket: WebSocket, task_id: int):
    """Stream logs for a specific task via WebSocket."""
    await websocket.accept()
    queue = log_broadcaster.subscribe(task_id=task_id)

    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        log_broadcaster.unsubscribe(queue, task_id=task_id)
