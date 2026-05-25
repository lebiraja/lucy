"""Callback handler for forwarding LangGraph execution events to WebSocket.

This module provides an optional streaming callback that can be used to
send real-time node execution events through the LogBroadcaster.
"""

from __future__ import annotations

from app.services.logger import log_broadcaster


async def on_node_start(node_name: str, task_id: int) -> None:
    """Called when a LangGraph node begins execution."""
    await log_broadcaster.broadcast(
        message=f"Node '{node_name}' started",
        level="debug",
        source="langgraph",
        task_id=task_id,
    )


async def on_node_end(node_name: str, task_id: int) -> None:
    """Called when a LangGraph node completes execution."""
    await log_broadcaster.broadcast(
        message=f"Node '{node_name}' completed",
        level="debug",
        source="langgraph",
        task_id=task_id,
    )
