"""
Planning Agents for Level 0.5 temporary execution.

Temporary Claude-style planning agents that analyze the CEO's project
requirements and formulate a high-level architecture and workforce estimate.
"""

import json
import logging
from typing import Dict, Any
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.models import Agent, Project, PlanningSession

logger = logging.getLogger(__name__)


# --- Structured Output Schema ---

class ArchitectureComponent(BaseModel):
    name: str = Field(description="Name of the technical module/component")
    purpose: str = Field(description="Primary role in the system")
    technology: str = Field(description="Suggested tech stack (e.g. React, PostgreSQL)")
    complexity: int = Field(description="Module complexity, 1-10")

class WorkforceEstimate(BaseModel):
    cto: int = Field(default=1, description="Number of CTOs needed (usually 1)")
    manager: int = Field(description="Number of managers needed (one per major domain/module)")
    employee: int = Field(description="Total number of workers/employees needed")

class PlanningOutput(BaseModel):
    architecture_overview: str = Field(description="High-level architecture description")
    components: list[ArchitectureComponent] = Field(description="List of technical modules")
    workforce_estimate: WorkforceEstimate = Field(description="Estimated agents needed per role")
    risk_analysis: list[str] = Field(description="Top 3 project risks")


# --- Planning Phase Manager ---

class PlanningAgentManager:
    """Invokes temporary planning agents using structured extraction."""
    
    def __init__(self, db_agent: Agent):
        self.agent = db_agent
        self.llm = ChatOpenAI(
            model=db_agent.model_name or "default-model",
            api_key="EMPTY",
            base_url=f"{db_agent.endpoint}/v1",
            temperature=db_agent.temperature,
            max_tokens=db_agent.max_tokens,
            model_kwargs={"top_p": db_agent.top_p}
        )

    async def execute_planning_session(self, project: Project) -> PlanningOutput:
        """Run the level 0.5 architectural planning."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Level 0.5 Master Planning Agent. Given the project requirements, "
                       "design the high-level architecture, define the modules, and estimate the workforce "
                       "needed (CTOs, Managers, Employees) to deliver it. You must be precise."),
            ("human", "Project Title: {title}\nRequirements: {requirements}")
        ])

        structured_llm = self.llm.with_structured_output(PlanningOutput)
        chain = prompt | structured_llm

        result = await chain.ainvoke({
            "title": project.title,
            "requirements": project.client_requirements
        })

        return result

    async def create_plan(self, project: Project) -> Dict[str, Any]:
        """Execute planning and return formatted output for workflow engine."""
        result = await self.execute_planning_session(project)
        
        # Convert to dictionary format expected by workflow
        return {
            "architecture": {
                "overview": result.architecture_overview,
                "components": [c.model_dump() for c in result.components],
            },
            "modules": [
                {"name": c.name, "description": c.purpose, "technology": c.technology, "complexity": c.complexity}
                for c in result.components
            ],
            "tech_stack": list(set(c.technology for c in result.components)),
            "workforce": {
                "cto": result.workforce_estimate.cto,
                "manager": result.workforce_estimate.manager,
                "employee": result.workforce_estimate.employee,
            },
            "risks": result.risk_analysis,
            "execution_plan": {"phases": ["planning", "development", "testing", "deployment"]},
            "complexity": sum(c.complexity for c in result.components) // max(len(result.components), 1),
        }
