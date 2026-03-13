"""
Worker Agent for Lucy Hierarchical Platform.

Executes specific Tasks assigned by a Manager, processes checklists,
and reports completion or blockers.
"""

import json
import logging
from typing import List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.models import Agent, Task, Checklist

logger = logging.getLogger(__name__)


# --- Structured Output Schema ---

class ChecklistUpdate(BaseModel):
    item: str = Field(description="The checklist item text")
    status: bool = Field(description="True if completed, False if blocked/incomplete")
    notes: str = Field(description="Notes or link to artifacts related to this item")

class WorkerExecutionOutput(BaseModel):
    output_summary: str = Field(description="Summary of work completed for the task")
    checklist_updates: List[ChecklistUpdate] = Field(description="Status of all assigned checklist items")
    needs_clarification: bool = Field(description="True if the worker is blocked and needs manager input")
    blocker_description: str = Field(description="Detail of what is blocking progress, if any")


# --- Worker Services ---

class WorkerAgentManager:
    """Manages Worker execution using LangChain structured outputs."""

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

    async def execute_task(self, task: Task, checklists: List[Checklist]) -> WorkerExecutionOutput:
        """Execute a task and update checklists."""
        
        checklist_str = "\n".join([f"- {c.title}" for c in checklists])
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an AI Software Engineer (Worker). Execute the assigned task. "
                       "You must meticulously address the provided checklist. "
                       "If you are blocked, clearly state why and set needs_clarification=True."),
            ("human", "Task Prompt: {prompt}\n\nMandaory Checklist:\n{checklist}")
        ])
        
        structured_llm = self.llm.with_structured_output(WorkerExecutionOutput)
        chain = prompt | structured_llm
        
        result = await chain.ainvoke({
            "prompt": task.prompt,
            "checklist": checklist_str
        })
        return result
