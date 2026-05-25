"""Delegation nodes (Levels 0, 2, 3) for hierarchical orchestration."""

import asyncio
from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.agent_nodes import run_agent_step

async def ceo_intake_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    prompt = state["prompt"]
    agents = state.get("agents", [])
    
    ceo = next((a for a in agents if a["role"] == "ceo"), None)
    if not ceo:
        return {}
        
    system_prompt = (
        "You are the Level 0 CEO Agent. Review the new project request and set "
        "strategic priorities and constraints for the planning layer.\n\n"
        f"Request:\n{prompt}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=ceo,
        prompt=system_prompt,
        step_order=step_order,
        step_label="ceo_intake",
    )
    
    # Prompt is augmented with CEO's strategic priorities for the planning layer
    updated_prompt = f"{prompt}\n\nCEO Strategic Priorities:\n{result.response}"
    return {
        "current_step_order": step_order,
        "prompt": updated_prompt
    }

async def cto_breakdown_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    raw_plan = state.get("project_plan", {}).get("raw_plan", "")
    
    cto = next((a for a in agents if a["role"] == "cto"), None)
    if not cto:
        return {}
        
    system_prompt = (
        "You are the Level 2 CTO Agent. Translate the Level 0.5 project plan into "
        "a concrete technical breakdown for the Manager layer.\n\n"
        f"Project Plan:\n{raw_plan}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=cto,
        prompt=system_prompt,
        step_order=step_order,
        step_label="cto_breakdown",
    )
    
    return {
        "current_step_order": step_order,
        "task_breakdown": [{"content": result.response}]
    }

async def manager_delegation_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    breakdown_list = state.get("task_breakdown", [])
    breakdown = breakdown_list[0].get("content", "") if breakdown_list else ""
    
    managers = [a for a in agents if "manager" in a["role"]]
    if not managers:
        return {}
        
    step_order = state.get("current_step_order", 0) + 1
    
    async def get_manager_checklist(manager):
        system_prompt = (
            f"You are the {manager['role']} Agent. Based on the CTO's technical breakdown, "
            "create a clear task checklist for your team to execute.\n\n"
            f"CTO Breakdown:\n{breakdown}"
        )
        return await run_agent_step(
            task_id=task_id,
            agent_dict=manager,
            prompt=system_prompt,
            step_order=step_order,
            step_label=f"{manager['role']}_checklist",
        )
        
    results = await asyncio.gather(*(get_manager_checklist(m) for m in managers))
    
    checklists = {str(res.agent_id): [{"content": res.response}] for res in results if res.status == "completed"}
    
    return {
        "current_step_order": step_order,
        "manager_checklists": checklists
    }

async def execution_fan_out_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    checklists = state.get("manager_checklists", {})
    
    employees = [a for a in agents if a["role"] in ("employee", "developer", "tester")]
    if not employees:
        return {}
        
    step_order = state.get("current_step_order", 0) + 1
    
    combined_checklists = "\n\n".join([f"Manager Tasks:\n{items[0]['content']}" for items in checklists.values() if items])
    if not combined_checklists:
        combined_checklists = "No specific tasks from managers. Execute the general CTO plan."
        
    async def get_execution(employee):
        system_prompt = (
            f"You are a {employee['role']} Agent. Execute the following tasks "
            "Provide your complete output.\n\n"
            f"Tasks:\n{combined_checklists}"
        )
        return await run_agent_step(
            task_id=task_id,
            agent_dict=employee,
            prompt=system_prompt,
            step_order=step_order,
            step_label="execution",
        )
        
    results = await asyncio.gather(*(get_execution(e) for e in employees))
    
    return {
        "current_step_order": step_order,
        "agent_responses": [res for res in results if res.status == "completed"]
    }

async def manager_review_node(state: TaskState) -> dict:
    return {"rework_count": state.get("rework_count", 0) + 1}

async def cto_synthesis_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    responses = state.get("agent_responses", [])
    
    cto = next((a for a in agents if a["role"] == "cto"), None)
    if not cto:
        return {}
        
    combined_execution = "\n\n---\n\n".join([f"From {r.agent_name}:\n{r.response}" for r in responses])
    
    system_prompt = (
        "You are the Level 2 CTO Agent. Synthesize the execution outputs from the employee layer "
        "into a cohesive final technical deliverable.\n\n"
        f"Execution Outputs:\n{combined_execution}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=cto,
        prompt=system_prompt,
        step_order=step_order,
        step_label="cto_synthesis",
    )
    
    return {
        "current_step_order": step_order,
        "final_output": result.response
    }

async def ceo_approval_node(state: TaskState) -> dict:
    task_id = state["task_id"]
    agents = state.get("agents", [])
    final_output = state.get("final_output", "")
    
    ceo = next((a for a in agents if a["role"] == "ceo"), None)
    if not ceo:
        return {}
        
    system_prompt = (
        "You are the Level 0 CEO Agent. Provide final approval and executive summary "
        "for the completed project deliverable.\n\n"
        f"Deliverable:\n{final_output}"
    )
    
    step_order = state.get("current_step_order", 0) + 1
    result = await run_agent_step(
        task_id=task_id,
        agent_dict=ceo,
        prompt=system_prompt,
        step_order=step_order,
        step_label="ceo_approval",
    )
    
    approved_output = f"# Executive Summary (CEO)\n{result.response}\n\n# Final Deliverable\n{final_output}"
    return {
        "current_step_order": step_order,
        "final_output": approved_output,
        "task_status": "completed"
    }
