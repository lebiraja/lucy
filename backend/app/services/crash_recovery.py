"""
Agent Crash Recovery & Data Persistence Service

Ensures data is never lost even when models crash or become unresponsive.
Provides automatic checkpointing and recovery mechanisms.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import Agent, Task, TaskStep, StepStatus, LogEntry, LogLevel, InfrastructureStatus


class CheckpointManager:
    """Manages automatic checkpointing of agent responses during execution."""
    
    def __init__(self):
        self.active_checkpoints = {}  # task_step_id -> checkpoint data
    
    async def save_checkpoint(
        self,
        task_step_id: int,
        partial_response: str,
        agent_id: int,
        metadata: dict = None
    ):
        """
        Save a checkpoint of partial response data.
        This ensures we never lose data even if the model crashes mid-response.
        """
        async with async_session() as session:
            result = await session.execute(
                select(TaskStep).where(TaskStep.id == task_step_id)
            )
            step = result.scalar_one_or_none()
            
            if step:
                # Store partial response in the database
                step.response = partial_response
                
                # Update checkpoint metadata
                checkpoint_data = {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "response_length": len(partial_response),
                    "is_partial": True,
                }
                if metadata:
                    checkpoint_data.update(metadata)
                
                step.step_metadata = checkpoint_data
                
                # Also update agent's last_checkpoint
                agent_result = await session.execute(
                    select(Agent).where(Agent.id == agent_id)
                )
                agent = agent_result.scalar_one_or_none()
                if agent:
                    agent.last_checkpoint = {
                        "task_step_id": task_step_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "response_length": len(partial_response),
                    }
                
                await session.commit()
                
                # Cache in memory for quick access
                self.active_checkpoints[task_step_id] = {
                    "response": partial_response,
                    "updated_at": time.time(),
                }
    
    async def finalize_checkpoint(self, task_step_id: int, final_response: str, duration_ms: int):
        """Mark a checkpoint as complete with the final response."""
        async with async_session() as session:
            result = await session.execute(
                select(TaskStep).where(TaskStep.id == task_step_id)
            )
            step = result.scalar_one_or_none()
            
            if step:
                step.response = final_response
                step.duration_ms = duration_ms
                step.status = StepStatus.COMPLETED
                
                # Update metadata to mark as complete
                if step.step_metadata:
                    step.step_metadata["is_partial"] = False
                    step.step_metadata["finalized_at"] = datetime.now(timezone.utc).isoformat()
                
                await session.commit()
        
        # Clear from memory cache
        self.active_checkpoints.pop(task_step_id, None)
    
    async def recover_checkpoint(self, task_step_id: int) -> Optional[str]:
        """Recover partial response from a previous checkpoint."""
        # Check memory cache first
        if task_step_id in self.active_checkpoints:
            return self.active_checkpoints[task_step_id]["response"]
        
        # Fallback to database
        async with async_session() as session:
            result = await session.execute(
                select(TaskStep).where(TaskStep.id == task_step_id)
            )
            step = result.scalar_one_or_none()
            
            if step and step.response:
                return step.response
        
        return None


class CrashRecoveryWrapper:
    """
    Wraps LLM calls with automatic crash detection and recovery.
    Ensures partial data is always saved.
    """
    
    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager
    
    async def execute_with_recovery(
        self,
        agent: Agent,
        task_step_id: int,
        execution_func: Callable,
        *args,
        **kwargs
    ) -> tuple[str, int, Optional[str]]:
        """
        Execute an LLM call with automatic recovery on failure.
        
        Returns:
            Tuple of (response, duration_ms, error_message)
        """
        start_time = time.perf_counter()
        partial_response = ""
        error_message = None
        
        try:
            # Check if there's a previous checkpoint to recover from
            recovered = await self.checkpoint_manager.recover_checkpoint(task_step_id)
            if recovered:
                await self._log_recovery(task_step_id, agent.id, len(recovered))
                partial_response = recovered
            
            # Execute the function (could be streaming or non-streaming)
            result = await execution_func(*args, **kwargs)
            
            # Handle both tuple and async iterator results
            if hasattr(result, '__aiter__'):
                # Streaming response
                async for chunk in result:
                    if chunk.get("content"):
                        partial_response += chunk["content"]
                        
                        # Save checkpoint every ~500ms or 100 chars
                        if len(partial_response) % 100 < 10:
                            await self.checkpoint_manager.save_checkpoint(
                                task_step_id,
                                partial_response,
                                agent.id
                            )
                    
                    if chunk.get("done"):
                        duration_ms = chunk.get("duration_ms", 0)
                        error_message = chunk.get("error")
                        break
            else:
                # Non-streaming response (tuple)
                partial_response, duration_ms = result
            
            # Finalize checkpoint
            await self.checkpoint_manager.finalize_checkpoint(
                task_step_id,
                partial_response,
                duration_ms
            )
            
            return partial_response, duration_ms, error_message
            
        except Exception as e:
            # On any error, save what we have and mark agent as crashed
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            error_message = str(e)
            
            # Save partial response even on crash
            if partial_response:
                await self.checkpoint_manager.save_checkpoint(
                    task_step_id,
                    partial_response,
                    agent.id,
                    {"error": error_message, "crashed": True}
                )
            
            # Update agent crash count
            await self._mark_agent_crash(agent.id, error_message)
            
            # Log the crash
            await self._log_crash(task_step_id, agent.id, error_message)
            
            return partial_response, duration_ms, error_message
    
    async def _mark_agent_crash(self, agent_id: int, error: str):
        """Mark an agent as crashed and increment crash counter."""
        async with async_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.id == agent_id)
            )
            agent = result.scalar_one_or_none()
            
            if agent:
                agent.crash_count += 1
                agent.infrastructure_status = InfrastructureStatus.OFFLINE
                agent.last_checkpoint = {
                    "crash_time": datetime.now(timezone.utc).isoformat(),
                    "error": error,
                }
                await session.commit()
    
    async def _log_crash(self, task_step_id: int, agent_id: int, error: str):
        """Log agent crash to database."""
        async with async_session() as session:
            # Get task_id from step
            result = await session.execute(
                select(TaskStep).where(TaskStep.id == task_step_id)
            )
            step = result.scalar_one_or_none()
            
            if step:
                log_entry = LogEntry(
                    task_id=step.task_id,
                    level=LogLevel.ERROR,
                    source=f"agent-{agent_id}",
                    message=f"Agent crashed during execution: {error}. Partial data preserved.",
                )
                session.add(log_entry)
                await session.commit()
    
    async def _log_recovery(self, task_step_id: int, agent_id: int, recovered_bytes: int):
        """Log successful recovery from checkpoint."""
        async with async_session() as session:
            result = await session.execute(
                select(TaskStep).where(TaskStep.id == task_step_id)
            )
            step = result.scalar_one_or_none()
            
            if step:
                log_entry = LogEntry(
                    task_id=step.task_id,
                    level=LogLevel.INFO,
                    source=f"agent-{agent_id}",
                    message=f"Recovered {recovered_bytes} bytes from previous checkpoint",
                )
                session.add(log_entry)
                await session.commit()


# Global singleton instances
checkpoint_manager = CheckpointManager()
crash_recovery = CrashRecoveryWrapper(checkpoint_manager)
