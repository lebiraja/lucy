"""
CEO Agent for Lucy Hierarchical Platform.

Uses LangChain with structured output to analyze project requirements,
determine if clarification is needed, and make high-level decisions.
"""

import json
import logging
from typing import Optional, List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
# We use standard langchain chat models; for vLLM we can use ChatOpenAI connected to our local endpoint
from langchain_openai import ChatOpenAI

from app.models import Agent, Project
from app.services.agent_registry import get_fleet_status, check_workforce_sufficiency

logger = logging.getLogger(__name__)

# --- Structured Output Schema ---

class CeoAnalysisOutput(BaseModel):
    is_clear: bool = Field(description="Whether the project requirements are clear enough to proceed to planning.")
    clarification_questions: List[str] = Field(description="If not clear, a minimum list of questions to ask the user.")
    project_scope: str = Field(description="A synthesized summary of the project scope if clear.")
    complexity_estimate: int = Field(description="Estimated complexity from 1-10.")

class CeoReviewOutput(BaseModel):
    approved: bool = Field(description="Whether the architecture proposed by planning agents is sound.")
    feedback: str = Field(description="Constructive feedback if rejected.")

# --- CEO Services ---

class CeoAgentManager:
    """Manages CEO decision-making using LangChain structured outputs."""

    def __init__(self, db_agent: Agent):
        self.agent = db_agent
        # Connect ChatOpenAI to vLLM endpoint
        self.llm = ChatOpenAI(
            model=db_agent.model_name or "default-model",
            api_key="EMPTY",
            base_url=f"{db_agent.endpoint}/v1",
            temperature=db_agent.temperature,
            max_tokens=db_agent.max_tokens,
            model_kwargs={"top_p": db_agent.top_p}
        )

    async def analyze_requirements(self, project: Project) -> CeoAnalysisOutput:
        """Analyze client requirements and decide if clarification is needed."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are the CEO of an elite software development multi-agent organization. "
                       "Your job is to analyze client requirements and decide if they are actionable, "
                       "or if you must ask clarifying questions. Be concise and decisive."),
            ("human", "Project Title: {title}\nRequirements: {requirements}")
        ])

        # We use with_structured_output if the model supports it. Many vLLM models support tool calling now.
        # Alternatively, we can prompt for JSON and parse. Assuming the model supports structured outputs (OpenAI-compatible).
        structured_llm = self.llm.with_structured_output(CeoAnalysisOutput)
        chain = prompt | structured_llm
        
        result = await chain.ainvoke({
            "title": project.title,
            "requirements": project.client_requirements
        })
        return result

    async def review_plan(self, project: Project, planning_output: dict) -> CeoReviewOutput:
        """Review the Level 0.5 planning output."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are the CEO. Review the proposed architecture and workforce estimate for the project. "
                       "Approve it if it makes sense. If fundamentally flawed, reject and provide feedback."),
            ("human", "Project: {title}\nPlan: {plan}")
        ])
        
        structured_llm = self.llm.with_structured_output(CeoReviewOutput)
        chain = prompt | structured_llm
        
        result = await chain.ainvoke({
            "title": project.title,
            "plan": json.dumps(planning_output, indent=2)
        })
        return result
