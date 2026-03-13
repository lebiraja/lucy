"""
Continuous Model Monitoring Service

Monitors all agents continuously:
- Auto-detects and updates context windows
- Tracks agent health and availability
- Monitors response times and patterns
- Auto-recovers from failures
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import Agent, InfrastructureStatus, OperationalStatus
from app.services.llm_client import check_health, fetch_model_info
from app.services.logger import log_broadcaster


class AgentMonitor:
    """Continuously monitors agents for health, capabilities, and context windows."""
    
    def __init__(self, check_interval: int = 30):
        """
        Args:
            check_interval: Seconds between health checks (default: 30s)
        """
        self.check_interval = check_interval
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the background monitoring task."""
        if self.is_running:
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        print(f"[AgentMonitor] Started continuous monitoring (interval: {self.check_interval}s)")
    
    async def stop(self):
        """Stop the background monitoring task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[AgentMonitor] Stopped continuous monitoring")
    
    async def _monitoring_loop(self):
        """Main monitoring loop that runs continuously."""
        while self.is_running:
            try:
                await self._check_all_agents()
            except Exception as e:
                print(f"[AgentMonitor] Error in monitoring loop: {e}")
            
            # Wait before next check
            await asyncio.sleep(self.check_interval)
    
    async def _check_all_agents(self):
        """Check health and capabilities of all active agents."""
        async with async_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.is_active == True)
            )
            agents = result.scalars().all()
            
            if not agents:
                return
            
            # Check all agents in parallel - each gets its own session
            tasks = [self._check_single_agent(agent) for agent in agents]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_single_agent(self, agent: Agent):
        """
        Check a single agent's health and update its configuration.
        Auto-detects context window if not set or changed.
        Uses its own isolated database session for thread safety.
        """
        # Each agent check gets its own session for parallel execution
        async with async_session() as session:
            try:
                # Re-fetch agent in this session to avoid detached instance issues
                result = await session.execute(
                    select(Agent).where(Agent.id == agent.id)
                )
                agent = result.scalar_one_or_none()
                if not agent:
                    return
                
                # 1. Health check
                is_online, latency_ms, error = await check_health(agent.endpoint)
                
                # Update infrastructure status
                new_status = InfrastructureStatus.ONLINE if is_online else InfrastructureStatus.OFFLINE
                status_changed = agent.infrastructure_status != new_status
                
                agent.infrastructure_status = new_status
                agent.is_warm = is_online
                agent.last_heartbeat = datetime.now(timezone.utc)
                
                if is_online and latency_ms:
                    # Update rolling average response time
                    if agent.avg_response_time_ms:
                        agent.avg_response_time_ms = (agent.avg_response_time_ms * 0.8) + (latency_ms * 0.2)
                    else:
                        agent.avg_response_time_ms = latency_ms
                
                # 2. Detect/update model capabilities if online
                if is_online:
                    await self._update_model_capabilities(agent)
                    
                    # Log recovery if agent came back online
                    if status_changed:
                        await log_broadcaster.broadcast(
                            message=f"✓ Agent {agent.name} is back online (latency: {latency_ms}ms)",
                            level="info",
                            source="monitor",
                        )
                else:
                    # Log if agent went offline
                    if status_changed:
                        await log_broadcaster.broadcast(
                            message=f"⚠ Agent {agent.name} is offline: {error}",
                            level="warning",
                            source="monitor",
                        )
                        
                        # Auto-adjust operational status if too many crashes
                        if agent.crash_count >= 3:
                            agent.operational_status = OperationalStatus.FAILED
                            await log_broadcaster.broadcast(
                                message=f"❌ Agent {agent.name} marked as FAILED (crash count: {agent.crash_count})",
                                level="error",
                                source="monitor",
                            )
                
                await session.commit()
                
            except Exception as e:
                print(f"[AgentMonitor] Error checking agent {agent.name}: {e}")
    
    async def _update_model_capabilities(self, agent: Agent):
        """
        Auto-detect and update model capabilities like context window.
        Only updates if not manually set or if significantly different.
        """
        try:
            info = await fetch_model_info(agent.endpoint)
            
            # Update model name if not set
            if not agent.model_name and info.get("model_name"):
                agent.model_name = info["model_name"]
                print(f"[AgentMonitor] Detected model for {agent.name}: {agent.model_name}")
            
            # Update context window if detected and different
            detected_context = info.get("context_window") or info.get("max_model_len")
            if detected_context:
                # Only update if significantly different (>10% change) or not set
                if not agent.context_window_tokens:
                    agent.context_window_tokens = detected_context
                    # Auto-adjust max_tokens to 40% of context
                    agent.max_tokens = max(min(int(detected_context * 0.4), 2048), 256)
                    
                    print(f"[AgentMonitor] Updated {agent.name} context window: {detected_context} tokens")
                    
                    await log_broadcaster.broadcast(
                        message=f"📊 Agent {agent.name}: Detected context window = {detected_context} tokens, adjusted max_tokens = {agent.max_tokens}",
                        level="info",
                        source="monitor",
                    )
                elif abs(detected_context - agent.context_window_tokens) / agent.context_window_tokens > 0.1:
                    old_context = agent.context_window_tokens
                    agent.context_window_tokens = detected_context
                    agent.max_tokens = max(min(int(detected_context * 0.4), 2048), 256)
                    
                    print(f"[AgentMonitor] Updated {agent.name} context window: {old_context} -> {detected_context}")
                    
                    await log_broadcaster.broadcast(
                        message=f"📊 Agent {agent.name}: Context window changed {old_context} -> {detected_context} tokens",
                        level="info",
                        source="monitor",
                    )
        
        except Exception as e:
            # Not critical, just log
            print(f"[AgentMonitor] Could not fetch model info for {agent.name}: {e}")


class PerformanceTracker:
    """Tracks agent performance metrics over time."""
    
    def __init__(self):
        self.response_history = {}  # agent_id -> list of (timestamp, duration_ms, success)
    
    def record_response(self, agent_id: int, duration_ms: int, success: bool):
        """Record a response time for analytics."""
        if agent_id not in self.response_history:
            self.response_history[agent_id] = []
        
        self.response_history[agent_id].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "success": success,
        })
        
        # Keep only last 100 responses per agent
        if len(self.response_history[agent_id]) > 100:
            self.response_history[agent_id] = self.response_history[agent_id][-100:]
    
    def get_agent_stats(self, agent_id: int) -> dict:
        """Get performance statistics for an agent."""
        history = self.response_history.get(agent_id, [])
        if not history:
            return {
                "total_requests": 0,
                "success_rate": 0.0,
                "avg_response_ms": 0.0,
            }
        
        total = len(history)
        successes = sum(1 for r in history if r["success"])
        avg_duration = sum(r["duration_ms"] for r in history) / total
        
        return {
            "total_requests": total,
            "success_rate": successes / total,
            "avg_response_ms": round(avg_duration, 2),
            "last_24h": len([r for r in history if self._is_recent(r["timestamp"], hours=24)]),
        }
    
    def _is_recent(self, timestamp_str: str, hours: int) -> bool:
        """Check if a timestamp is within the last N hours."""
        try:
            ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return (now - ts).total_seconds() < (hours * 3600)
        except Exception:
            return False


# Global singleton instances
agent_monitor = AgentMonitor(check_interval=30)  # Check every 30 seconds
performance_tracker = PerformanceTracker()
