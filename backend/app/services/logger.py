"""Real-time log broadcasting service using asyncio."""

import asyncio
import json
from datetime import datetime, timezone
from app.schemas import LogBroadcast


class LogBroadcaster:
    """Manages WebSocket connections and broadcasts log messages.

    Two separate channels:
    - "global": subscribers that want ALL messages (no task_id filter)
    - "task_{id}": subscribers that want messages for a specific task only
    """

    def __init__(self):
        self._global_subs: set[asyncio.Queue] = set()
        self._task_subs: dict[int, set[asyncio.Queue]] = {}

    def subscribe(self, task_id: int | None = None) -> asyncio.Queue:
        """Subscribe to log events. Returns a queue to listen on.

        - task_id=None  → global subscriber (receives ALL log messages)
        - task_id=N     → task-specific subscriber (receives only that task's messages)
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if task_id is not None:
            if task_id not in self._task_subs:
                self._task_subs[task_id] = set()
            self._task_subs[task_id].add(queue)
        else:
            self._global_subs.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue, task_id: int | None = None):
        """Remove a subscriber queue."""
        if task_id is not None:
            self._task_subs.get(task_id, set()).discard(queue)
        else:
            self._global_subs.discard(queue)

    async def broadcast(
        self,
        message: str,
        level: str = "info",
        source: str = "system",
        task_id: int | None = None,
    ):
        """Broadcast a log message to all relevant subscribers.

        - Task-specific message (task_id set): sent to task channel + global channel.
        - System message (no task_id): sent to global channel only.
        """
        log = LogBroadcast(
            task_id=task_id,
            level=level,
            source=source,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        payload = log.model_dump_json()

        # Send to task-specific subscribers
        if task_id is not None:
            for queue in list(self._task_subs.get(task_id, set())):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        # Always send to global subscribers (they see everything)
        for queue in list(self._global_subs):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


# Singleton instance
log_broadcaster = LogBroadcaster()
