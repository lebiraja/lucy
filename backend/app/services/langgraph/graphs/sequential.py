"""Sequential strategy graph — linear chain of agents."""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.agent_nodes import run_agent_step
from app.services.langgraph.nodes.utility_nodes import log_step
from app.services.langgraph.nodes.output_nodes import build_structured_output_node


async def sequential_chain_node(state: TaskState) -> dict:
    """Run agents one after another, each building on the previous response."""
    task_id = state["task_id"]
    agents = state["agents"]
    prompt = state["prompt"]
    workspace_dir = state.get("workspace_dir")
    conversation_history = state.get("conversation_history") or []

    accumulated = prompt
    final_response = ""
    all_results = []

    await log_step(task_id, f"Starting SEQUENTIAL execution with {len(agents)} agents")

    for i, agent_dict in enumerate(agents):
        result = await run_agent_step(
            task_id, agent_dict, accumulated, step_order=i,
            workspace_dir=workspace_dir,
            conversation_history=conversation_history if i == 0 else None,
        )
        all_results.append(result)

        if result.status == "failed":
            await log_step(
                task_id,
                f"Sequential chain broken at step {i + 1} ({agent_dict.get('name', 'unknown')})",
                level="error",
            )
            return {
                "task_status": "failed",
                "final_output": f"Chain failed at step {i + 1} ({agent_dict.get('name')}): {result.response}",
                "agent_responses": all_results,
            }

        final_response = result.response
        accumulated = (
            f"Original prompt: {prompt}\n\n"
            f"Previous agent ({result.agent_name}) responded:\n{result.response}\n\n"
            "Please continue building on this response."
        )

    await log_step(task_id, "Sequential execution completed successfully")
    return {
        "task_status": "completed",
        "final_output": final_response,
        "agent_responses": all_results,
    }


def build_sequential_graph() -> StateGraph:
    graph = StateGraph(TaskState)
    graph.add_node("sequential_chain", sequential_chain_node)
    graph.add_node("structured_output", build_structured_output_node)
    graph.add_edge(START, "sequential_chain")
    graph.add_edge("sequential_chain", "structured_output")
    graph.add_edge("structured_output", END)
    return graph
