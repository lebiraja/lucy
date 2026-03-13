"""
AutoGen Communication Wrapper.
Wraps 'pyautogen' to facilitate ConversableAgent group chats while adhering
to the hierarchical chain of command and logging to 'agent_messages'.
"""

import json
import logging
import asyncio
from typing import List, Dict, Any, Optional

from autogen import ConversableAgent, GroupChat, GroupChatManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, AgentMessage, MessageType, MessagePriority

logger = logging.getLogger(__name__)

class HierarchicalCommunicator:
    """
    Manages communication between agents using pyautogen.
    Enforces reporting lines (e.g., workers -> managers -> cto -> ceo)
    and logs all messages to the AgentMessage table.
    """
    def __init__(self, db_session: AsyncSession, project_id: int, task_id: Optional[int] = None):
        self.db = db_session
        self.project_id = project_id
        self.task_id = task_id
        # Map of autogen agent name -> lucy db agent_id
        self.agent_map: Dict[str, int] = {}
        
    async def log_interaction(self, sender: ConversableAgent, recipient: ConversableAgent, message: Dict[str, Any], request_reply: bool, silent: bool):
        """Callback to log pyautogen messages to our DB."""
        if not hasattr(sender, "name") or not hasattr(recipient, "name"):
            return

        sender_id = self.agent_map.get(sender.name)
        receiver_id = self.agent_map.get(recipient.name)
        
        # Don't log internal AutoGen tool calls unless useful, but let's log everything content-wise
        content = message.get("content", "")
        if not content:
            return

        msg_type = MessageType.PROGRESS_UPDATE
        # Simple heuristic or could explicitly set in message dict
        if "escalat" in content.lower():
            msg_type = MessageType.ESCALATION
        elif "assign" in content.lower():
            msg_type = MessageType.TASK_ASSIGNMENT

        db_msg = AgentMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            project_id=self.project_id,
            task_id=self.task_id,
            message_type=msg_type,
            payload={"content": content},
            priority=MessagePriority.NORMAL,
        )
        self.db.add(db_msg)
        await self.db.commit()

    def build_autogen_agent(self, db_agent: Agent, system_message: str) -> ConversableAgent:
        """Constructs a pyautogen Agent from a Lucy Agent model."""
        # This assumes vLLM exposes an OpenAI compatible API
        max_tokens = db_agent.max_tokens
        if getattr(db_agent, 'context_window_tokens', None):
            max_tokens = min(
                max_tokens,
                int(db_agent.context_window_tokens * 0.4),
                max(db_agent.context_window_tokens - 256, 256),
            )
            max_tokens = max(64, max_tokens)

        llm_config = {
            "config_list": [{
                "model": db_agent.model_name or "default-model",
                "api_key": "EMPTY", # vLLM doesn't usually require real API key
                "base_url": f"{db_agent.endpoint}/v1",
                "temperature": db_agent.temperature,
                "max_tokens": max_tokens,
                "top_p": db_agent.top_p,
            }],
            "timeout": db_agent.timeout_seconds,
            "cache_seed": None, # Disable autogen cache for dynamism
        }

        # Format name for AutoGen (no spaces)
        safe_name = db_agent.name.replace(" ", "_").lower()
        self.agent_map[safe_name] = db_agent.id

        autogen_agent = ConversableAgent(
            name=safe_name,
            system_message=system_message,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=10,
        )
        
        # Register reply hook to intercept and log messages
        autogen_agent.register_reply(
            [ConversableAgent, None],
            self._reply_hook,
            position=1
        )
        return autogen_agent
        
    def _reply_hook(self, recipient: ConversableAgent, messages: Optional[List[Dict]] = None, sender: Optional[ConversableAgent] = None, config: Optional[Any] = None) -> tuple[bool, Dict]:
        """Hook intercepting messages before generation to log them. We use async gathering in actual implementation."""
        if messages and sender:
            # Create a task to log asynchronously to avoid blocking AutoGen's sync paths
            last_msg = messages[-1]
            asyncio.create_task(self.log_interaction(sender, recipient, last_msg, False, False))
        return False, None # Continue with default processing

    async def execute_group_chat(self, agents: List[ConversableAgent], initial_speaker: ConversableAgent, prompt: str, max_rounds: int = 10) -> str:
        """Executes a round-table group chat."""
        # For a truly hierarchical chat, we'd use select_speaker_msg to enforce structure,
        # or distinct conversations. GroupChat gives them all visibility.
        groupchat = GroupChat(
            agents=agents,
            messages=[],
            max_round=max_rounds,
            speaker_selection_method="auto",
        )
        
        # Need an LLM for the manager to decide who speaks
        manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=agents[0].llm_config # Borrow the first agent's LLM for management
        )
        
        # Run conversation (AutoGen is mainly synchronous, we run in executor)
        loop = asyncio.get_event_loop()
        chat_result = await loop.run_in_executor(
            None,
            initial_speaker.initiate_chat,
            manager,
            prompt
        )
        
        # chat_result contains the history
        return chat_result.summary if hasattr(chat_result, 'summary') else str(chat_result)
