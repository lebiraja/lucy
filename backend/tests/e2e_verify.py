"""
End-to-End Verification Script for Lucy Platform.

This script tests the full lifecycle by interacting with the FastAPI backend.
It creates agents, registers them, submits a project, and verifies state changes.
"""

import httpx
import asyncio
import time

API_BASE = "http://localhost:8000/api"

async def register_agents(client):
    print("Registering mock agents...")
    agents = [
        {"name": "Alice-CEO", "endpoint": "http://mock-ceo:9001", "role": "ceo"},
        {"name": "Bob-CTO", "endpoint": "http://mock-cto:9002", "role": "cto"},
        {"name": "Charlie-Manager", "endpoint": "http://mock-manager:9003", "role": "manager"},
        {"name": "Dave-Worker", "endpoint": "http://mock-worker:9004", "role": "employee"}
    ]
    
    agent_ids = []
    for a in agents:
        resp = await client.post(f"{API_BASE}/agents/register", json=a)
        if resp.status_code == 201 or resp.status_code == 200:
            agent = resp.json()
            agent_ids.append(agent["id"])
            print(f"Registered {a['name']} with ID: {agent['id']}")
        else:
            print(f"Failed to register {a['name']}: {resp.text}")
    return agent_ids

async def check_fleet_status(client):
    print("Checking fleet status...")
    resp = await client.get(f"{API_BASE}/agents/fleet-status")
    print("Fleet Status:", resp.json())

async def create_project(client):
    print("Creating client project...")
    data = {
        "title": "E2E Verification Prototype",
        "client_requirements": "Build a comprehensive mock ecosystem to verify the LangGraph workflow engine and hierarchical communications.",
    }
    resp = await client.post(f"{API_BASE}/projects", json=data)
    if str(resp.status_code).startswith("2"):
        proj = resp.json()
        print(f"Project Created (ID: {proj['id']}) - Status: {proj['status']}")
        return proj["id"]
    else:
        print(f"Failed to create project: {resp.text}")
        return None

async def verify():
    async with httpx.AsyncClient() as client:
        print("Waiting for server to be ready...")
        try:
            await client.get(f"{API_BASE}/health")
        except Exception:
            print("Server not reachable. Make sure uvicorn is running.")
            return

        agent_ids = await register_agents(client)
        await check_fleet_status(client)
        
        project_id = await create_project(client)
        
        if project_id and len(agent_ids) > 0:
            # Assign CEO
            ceo_id = agent_ids[0]
            print(f"Assigning CEO (ID: {ceo_id}) to Project...")
            resp = await client.post(f"{API_BASE}/projects/{project_id}/assign-ceo?ceo_agent_id={ceo_id}")
            print(f"Assign CEO response: {resp.status_code}")
            
            # Start planning
            print(f"Triggering start-planning on Project...")
            resp = await client.post(f"{API_BASE}/projects/{project_id}/start-planning")
            print(f"Start Planning response: {resp.status_code}")
            
            # Check status
            resp = await client.get(f"{API_BASE}/projects/{project_id}")
            proj = resp.json()
            print(f"Final Project Status: {proj['status']}")

if __name__ == "__main__":
    asyncio.run(verify())
