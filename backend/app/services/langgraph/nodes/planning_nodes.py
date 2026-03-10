"""Planning layer nodes (Level 0.5) for the hierarchical orchestration engine."""

import json
from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.agent_nodes import run_agent_step
from app.services.langgraph.nodes.routing_nodes import extract_json

async def questioning_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    prompt = state["prompt"]
    agents = state.get("agents", [])
    
    questioner = next((a for a in agents if a["role"] == "questioner"), None)
    if not questioner:
        # If no questioner, skip
        return {"current_step_order": state.get("current_step_order", 0)}
        
    system_prompt = (
        "You are the Level 0.5 Questioning Agent. Your job is to analyze the "
        "user's project requirements and ask 3-5 critical follow-up questions "
        "to clarify ambiguities before planning begins.\n\n"
        f"Project Requirements:\n{prompt}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=questioner,
        prompt=system_prompt,
        step_order=step_order,
        step_label="questioning",
    )
    
    return {
        "current_step_order": step_order,
        "hierarchy_results": [
            {"phase": "planning_questions", "content": result.response}
        ]
    }

async def planning_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    prompt = state["prompt"]
    agents = state.get("agents", [])
    hierarchy_results = state.get("hierarchy_results", [])
    
    questions = next((r["content"] for r in hierarchy_results if r.get("phase") == "planning_questions"), "")
    
    planner = next((a for a in agents if a["role"] == "planner"), None)
    if not planner:
        return {"current_step_order": state.get("current_step_order", 0)}
        
    system_prompt = (
        "You are the Level 0.5 Planning Agent. Your job is to create a detailed development "
        "plan and system architecture based on the user's requirements.\n\n"
        f"Requirements:\n{prompt}\n\n"
        f"Analysis/Questions:\n{questions}\n\n"
        "Output a structured project plan."
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=planner,
        prompt=system_prompt,
        step_order=step_order,
        step_label="planning",
    )
    
    return {
        "current_step_order": step_order,
        "project_plan": {"raw_plan": result.response}
    }

async def allocation_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    raw_plan = state.get("project_plan", {}).get("raw_plan", "")
    
    planner = next((a for a in agents if a["role"] == "planner"), None)
    if not planner:
        return {"current_step_order": state.get("current_step_order", 0)}
        
    system_prompt = (
        "Based on the following project plan, determine how many agents of each role are needed. "
        "Available roles: cto, cfo, backend_manager, frontend_manager, qa_manager, developer, tester.\n\n"
        f"Plan:\n{raw_plan}\n\n"
        "Output ONLY valid JSON in this format: {\"allocation\": {\"role_name\": count}}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=planner,
        prompt=system_prompt,
        step_order=step_order,
        step_label="allocation",
    )
    
    try:
        json_str = extract_json(result.response)
        allocation_data = json.loads(json_str)
        allocation = allocation_data.get("allocation", {})
    except Exception:
        allocation = {"backend_manager": 1, "developer": 1} # fallback
        
    return {
        "current_step_order": step_order,
        "agent_allocation": allocation
    }
