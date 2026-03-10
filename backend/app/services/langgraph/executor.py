"""Graph executor — builds, caches, and invokes LangGraph strategy graphs.

This is the central entry point called by orchestrator.execute_task().
Each strategy has its own compiled graph cached for reuse.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from app.services.langgraph.state import TaskState
from app.services.langgraph.graphs.sequential import build_sequential_graph
from app.services.langgraph.graphs.parallel import build_parallel_graph
from app.services.langgraph.graphs.dynamic import build_dynamic_graph
from app.services.langgraph.graphs.council import build_council_graph


class GraphExecutor:
    """Builds and manages LangGraph strategy graphs with checkpointing.

    Usage:
        result = await graph_executor.run(initial_state)
    """

    def __init__(self) -> None:
        self._checkpointer = MemorySaver()
        self._graphs = {
            "sequential": build_sequential_graph().compile(
                checkpointer=self._checkpointer,
            ),
            "parallel": build_parallel_graph().compile(
                checkpointer=self._checkpointer,
            ),
            "dynamic": build_dynamic_graph().compile(
                checkpointer=self._checkpointer,
            ),
            "council": build_council_graph().compile(
                checkpointer=self._checkpointer,
            ),
        }

    async def run(self, state: TaskState) -> TaskState:
        """Invoke the appropriate strategy graph.

        Args:
            state: Initial TaskState with task_id, prompt, strategy, agents.

        Returns:
            Final TaskState after graph execution.

        Raises:
            ValueError: If the strategy is not recognized.
        """
        strategy = state["strategy"]
        graph = self._graphs.get(strategy)
        if not graph:
            raise ValueError(f"Unknown strategy: {strategy}")

        config = {
            "configurable": {
                "thread_id": f"task-{state['task_id']}",
            }
        }
        result = await graph.ainvoke(state, config=config)
        return result

    def get_graph(self, strategy: str):
        """Get a compiled graph by strategy name (for inspection/streaming)."""
        return self._graphs.get(strategy)


# Singleton — initialized on first import
graph_executor = GraphExecutor()
