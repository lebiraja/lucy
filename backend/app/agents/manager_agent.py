"""
Manager Agent for Lucy Hierarchical Platform.

Receives a ProjectModule from the CTO, breaks it down into actionable Tasks,
assigns them to Workers, and monitors completion via Checklists.
"""

import json
import logging
from typing import List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.models import Agent, ProjectModule, Task, Checklist

logger = logging.getLogger(__name__)


# --- Structured Output Schema ---

class DerivedTask(BaseModel):
    title: str = Field(description="Actionable title for the task")
    description: str = Field(description="Detailed instructions for the worker")
    checklists: List[str] = Field(description="Validation steps the worker must complete for this task")

class ManagerDelegationOutput(BaseModel):
    tasks: List[DerivedTask] = Field(description="List of tasks to be assigned to workers")


# --- Manager Services ---

class ManagerAgentManager:
    """Manages Manager delegation using LangChain structured outputs."""

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

    async def breakdown_module(self, module: ProjectModule, cto_strategy: str) -> ManagerDelegationOutput:
        """Break down a module into specific tasks with checklists."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an Engineering Manager. You have been assigned a technical module "
                       "by the CTO. Break it down into clear, independent tasks that can be "
                       "executed by your workers. For each task, define strict checklist items "
                       "that dictate when the task is considered 'done'."),
            ("human", "Module Name: {name}\nDescription: {description}\nTech Stack: {tech}\n\n"
                      "CTO Strategy Notes:\n{notes}")
        ])
        
        structured_llm = self.llm.with_structured_output(ManagerDelegationOutput)
        chain = prompt | structured_llm
        
        result = await chain.ainvoke({
            "name": module.name,
            "description": module.description,
            "tech": module.technology,
            "notes": cto_strategy
        })
        return result
