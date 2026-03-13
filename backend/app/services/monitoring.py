"""
Hierarchical Monitoring & Reporting System.

Aggregates checklists, task completions, and agent statuses
up the chain: Worker -> Manager -> CTO -> CEO.
"""

import logging
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List

from app.models import (
    Project, ProjectModule, TaskStatus, ModuleStatus, ProjectStatus, 
    Checklist, AgentMessage, MessageType
)

logger = logging.getLogger(__name__)


async def generate_project_report(session: AsyncSession, project_id: int) -> Dict[str, Any]:
    """Generates a hierarchical completion report for the CEO dashboard."""
    
    project = await session.get(Project, project_id)
    if not project:
        return {}

    # Get modules with their assigned managers
    module_query = select(ProjectModule).where(
        ProjectModule.project_id == project_id
    ).options(selectinload(ProjectModule.assigned_manager))
    
    modules = (await session.execute(module_query)).scalars().all()
    
    # Calculate rollup metrics
    total_modules = len(modules)
    completed_modules = 0
    
    module_details = []
    for mod in modules:
        if mod.status == ModuleStatus.COMPLETED:
            completed_modules += 1
            
        module_details.append({
            "id": mod.id,
            "name": mod.name,
            "complexity": mod.complexity,
            "status": mod.status.value,
            "assigned_manager": mod.assigned_manager.name if mod.assigned_manager else None,
        })

    # Get unread escalations/blockers targeting the CEO or CTO
    escalations_query = select(AgentMessage).where(
        and_(
            AgentMessage.project_id == project_id,
            AgentMessage.message_type == MessageType.ESCALATION,
            AgentMessage.is_read == False
        )
    ).order_by(AgentMessage.timestamp.desc())
    
    escalations = (await session.execute(escalations_query)).scalars().all()
    
    return {
        "project_id": project.id,
        "title": project.title,
        "status": project.status.value,
        "overall_progress_pct": round(completed_modules / total_modules * 100) if total_modules > 0 else 0,
        "modules": module_details,
        "active_escalations": len(escalations),
        "escalation_details": [{"id": e.id, "message": e.payload.get("content")} for e in escalations]
    }


async def check_deadline_risks(session: AsyncSession, project_id: int) -> bool:
    """Checks if a project is at risk of missing its deadline based on module progress."""
    # Placeholder for more complex risk logic (e.g., comparing module complexity vs time remaining)
    project = await session.get(Project, project_id)
    if not project or not project.deadline:
        return False
        
    # If 50% of time has passed but < 20% of modules are done, it's at risk
    # This is a simplified placeholder hook for the workflow engine
    return False 
