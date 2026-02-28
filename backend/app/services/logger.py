"""Real-time log broadcasting service using asyncio."""

import asyncio
import json
from datetime import datetime, timezone
from app.schemas import LogBroadcast


class LogBroadcaster:
    """Manages WebSocket connections and broadcasts log messages."""

    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = {
            "global": set(),
        }

    def subscribe(self, task_id: int | None = None) -> asyncio.Queue:
        """Subscribe to log events. Returns a queue to listen on."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        channel = f"task_{task_id}" if task_id else "global"
        if channel not in self._subscribers:
            self._subscribers[channel] = set()
        self._subscribers[channel].add(queue)
        self._subscribers["global"].add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue, task_id: int | None = None):
        """Remove a subscriber queue."""
        channel = f"task_{task_id}" if task_id else "global"
        self._subscribers.get(channel, set()).discard(queue)
        self._subscribers["global"].discard(queue)

    async def broadcast(
        self,
        message: str,
        level: str = "info",
        source: str = "system",
        task_id: int | None = None,
    ):
        """Broadcast a log message to all relevant subscribers."""
        log = LogBroadcast(
            task_id=task_id,
            level=level,
            source=source,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        payload = log.model_dump_json()

        # Send to task-specific subscribers
        if task_id:
            channel = f"task_{task_id}"
            for queue in list(self._subscribers.get(channel, set())):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        # Send to global subscribers (but avoid duplicates)
        if not task_id:
            for queue in list(self._subscribers.get("global", set())):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
        else:
            # For task-specific messages, also send to global subs
            # that aren't already in the task channel
            task_channel = self._subscribers.get(f"task_{task_id}", set())
            for queue in list(self._subscribers.get("global", set())):
                if queue not in task_channel:
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        pass


# Singleton instance
log_broadcaster = LogBroadcaster()
