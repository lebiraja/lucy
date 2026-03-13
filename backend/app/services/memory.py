"""
Memory System for Hierarchical Agents.
Provides short-term memory (execution context) and global project memory via Redis.
"""

import os
import json
import logging
import redis.asyncio as redis
from typing import Dict, Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class MemoryManager:
    """Manages Redis-backed memory for agents and projects."""
    
    def __init__(self):
        self.redis_url = settings.redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            logger.info(f"Connected to Redis at {self.redis_url}")

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def _agent_key(self, agent_id: int) -> str:
        return f"lucy:agent:{agent_id}:memory"
        
    def _project_key(self, project_id: int) -> str:
        return f"lucy:project:{project_id}:context"

    # --- Agent Short-Term Memory ---

    async def set_agent_context(self, agent_id: int, key: str, value: Any, expire: int = 86400):
        """Set a value in an agent's short-term memory (default 24h expiry)."""
        await self.connect()
        hkey = self._agent_key(agent_id)
        await self._redis.hset(hkey, key, json.dumps(value))
        await self._redis.expire(hkey, expire)

    async def get_agent_context(self, agent_id: int, key: str) -> Any:
        """Get a value from an agent's short-term memory."""
        await self.connect()
        data = await self._redis.hget(self._agent_key(agent_id), key)
        return json.loads(data) if data else None
        
    async def clear_agent_context(self, agent_id: int):
        await self.connect()
        await self._redis.delete(self._agent_key(agent_id))

    # --- Global Project Memory ---

    async def update_project_context(self, project_id: int, updates: Dict[str, Any]):
        """Update the global shared context for a project."""
        await self.connect()
        pkey = self._project_key(project_id)
        # Use a transaction/pipeline to update multiple fields safely
        async with self._redis.pipeline(transaction=True) as pipe:
            for k, v in updates.items():
                pipe.hset(pkey, k, json.dumps(v))
            await pipe.execute()
            
    async def get_project_context(self, project_id: int) -> Dict[str, Any]:
        """Fetch the entire global context for a project."""
        await self.connect()
        data = await self._redis.hgetall(self._project_key(project_id))
        return {k: json.loads(v) for k, v in data.items()}

# Global instance
memory = MemoryManager()
