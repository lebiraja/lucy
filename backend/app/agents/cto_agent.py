"""
CTO Agent for Lucy Hierarchical Platform.

Reviews the Level 0.5 technical plan relative to CEO requirements,
designs specific ProjectModules, and allocates Managers.
"""

import json
import logging
from typing import List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.models import Agent, Project, ProjectModule, ModuleStatus

logger = logging.getLogger(__name__)


# --- Structured Output Schema ---

class DerivedModule(BaseModel):
    name: str = Field(description="Name of the module")
    description: str = Field(description="Detailed technical description of what needs to be built")
    technology: str = Field(description="Core technology stack for this module")
    complexity: int = Field(description="Estimated complexity from 1-10")

class CTOStrategyOutput(BaseModel):
    modules: List[DerivedModule] = Field(description="List of concrete technical modules to build")
    strategy_notes: str = Field(description="Overall technical strategy notes for the managers")


# --- CTO Services ---

class CTOAgentManager:
    """Manages CTO strategy definition using LangChain structured outputs."""

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

    async def define_modules(self, project: Project, planning_output: dict) -> CTOStrategyOutput:
        """Break down the planning architecture into specific modules."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are the CTO. Given the project requirements and the approved Level 0.5 "
                       "architectural plan, define concrete, strictly bounded technical modules. "
                       "Each module will be assigned to a Manager to execute."),
            ("human", "Project: {title}\nRequirements: {requirements}\nArchitecture Plan: {plan}")
        ])

        structured_llm = self.llm.with_structured_output(CTOStrategyOutput)
        chain = prompt | structured_llm

        result = await chain.ainvoke({
            "title": project.title,
            "requirements": project.client_requirements,
            "plan": json.dumps(planning_output, indent=2)
        })
        return result

    async def create_modules(self, project: Project) -> dict:
        """Create modules from project planning data."""
        # Get planning session data from project metadata or create from requirements
        planning_output = {
            "architecture": project.task_metadata.get("architecture") if project.task_metadata else {},
            "workforce_estimate": project.required_agents or {},
        }
        
        result = await self.define_modules(project, planning_output)
        
        return {
            "modules": [m.model_dump() for m in result.modules],
            "strategy_notes": result.strategy_notes,
        }
