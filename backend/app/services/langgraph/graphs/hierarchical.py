"""Main hierarchical delegation graph for Lucy orchestration.

Flow:
ceo_intake -> planning_layer -> cto_breakdown -> manager_delegation -> 
    execution_fan_out -> manager_review -> cto_synthesis -> ceo_approval -> persist_result
"""

from langgraph.graph import StateGraph, END

from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.utility_nodes import persist_result_node
from app.services.langgraph.nodes.delegation_nodes import (
    ceo_intake_node,
    cto_breakdown_node,
    manager_delegation_node,
    execution_fan_out_node,
    manager_review_node,
    cto_synthesis_node,
    ceo_approval_node,
)
from app.services.langgraph.graphs.planning import build_planning_graph

def check_rework(state: TaskState) -> str:
    """Conditional edge: max 1 rework cycle."""
    count = state.get("rework_count", 0)
    if count < 1:
        # Simplification: we proceed to synthesis immediately
        return "cto_synthesis"
    return "cto_synthesis"

def build_hierarchical_graph() -> StateGraph:
    builder = StateGraph(TaskState)

    planning_subgraph = build_planning_graph().compile()

    builder.add_node("ceo_intake", ceo_intake_node)
    builder.add_node("planning_layer", planning_subgraph)
    builder.add_node("cto_breakdown", cto_breakdown_node)
    builder.add_node("manager_delegation", manager_delegation_node)
    builder.add_node("execution_fan_out", execution_fan_out_node)
    builder.add_node("manager_review", manager_review_node)
    builder.add_node("cto_synthesis", cto_synthesis_node)
    builder.add_node("ceo_approval", ceo_approval_node)
    builder.add_node("persist_result", persist_result_node)

    builder.set_entry_point("ceo_intake")
    builder.add_edge("ceo_intake", "planning_layer")
    builder.add_edge("planning_layer", "cto_breakdown")
    builder.add_edge("cto_breakdown", "manager_delegation")
    builder.add_edge("manager_delegation", "execution_fan_out")
    builder.add_edge("execution_fan_out", "manager_review")
    
    builder.add_conditional_edges("manager_review", check_rework)
    builder.add_edge("cto_synthesis", "ceo_approval")
    builder.add_edge("ceo_approval", "persist_result")
    builder.add_edge("persist_result", END)

    return builder
