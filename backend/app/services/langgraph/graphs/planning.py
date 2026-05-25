"""Level 0.5 Planning layer subgraph for hierarchical orchestration."""

from langgraph.graph import StateGraph

from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.planning_nodes import (
    questioning_node,
    planning_node,
    allocation_node,
)

def build_planning_graph() -> StateGraph:
    builder = StateGraph(TaskState)

    builder.add_node("questioning", questioning_node)
    builder.add_node("planning", planning_node)
    builder.add_node("allocation", allocation_node)

    builder.set_entry_point("questioning")
    builder.add_edge("questioning", "planning")
    builder.add_edge("planning", "allocation")
    builder.set_finish_point("allocation")

    return builder
