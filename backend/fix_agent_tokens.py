#!/usr/bin/env python3
"""
One-time script to update existing agents with safer max_tokens and context_window settings.
Also triggers auto-detection of model capabilities from their endpoints.

Run this after deploying the context window fixes.

Usage:
    cd backend && python3 fix_agent_tokens.py
"""

import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models import Agent
from app.services.llm_client import fetch_model_info


async def update_agents():
    """Update all agents to have safer token limits and auto-detect capabilities."""
    async with async_session() as session:
        result = await session.execute(select(Agent))
        agents = result.scalars().all()
        
        if not agents:
            print("No agents found in database.")
            return
        
        print(f"Found {len(agents)} agents. Updating token settings and detecting capabilities...\n")
        
        updated_count = 0
        for agent in agents:
            old_max_tokens = agent.max_tokens
            old_context = agent.context_window_tokens
            old_model_name = agent.model_name
            
            needs_update = False
            
            # Try to auto-detect model information
            try:
                print(f"Probing {agent.name} at {agent.endpoint}...")
                info = await fetch_model_info(agent.endpoint)
                
                # Update model name if not set
                if not agent.model_name and info.get("model_name"):
                    agent.model_name = info["model_name"]
                    print(f"  ✓ Detected model: {agent.model_name}")
                    needs_update = True
                
                # Update context window from detected value
                detected_context = info.get("context_window") or info.get("max_model_len")
                if detected_context:
                    agent.context_window_tokens = detected_context
                    # Adjust max_tokens to 40% of context
                    agent.max_tokens = max(min(int(detected_context * 0.4), 2048), 256)
                    print(f"  ✓ Detected context window: {detected_context} tokens")
                    print(f"  ✓ Adjusted max_tokens: {agent.max_tokens}")
                    needs_update = True
                
            except Exception as e:
                print(f"  ⚠ Could not probe {agent.name}: {e}")
                
                # Fallback: Update max_tokens if it's still at the old dangerous default
                if agent.max_tokens >= 1024:
                    agent.max_tokens = 512
                    needs_update = True
                    print(f"  ✓ Fallback: Set max_tokens to 512")
            
            if needs_update:
                print(f"✓ Updated {agent.name}:")
                if old_model_name != agent.model_name:
                    print(f"  - model_name: {old_model_name} → {agent.model_name}")
                if old_max_tokens != agent.max_tokens:
                    print(f"  - max_tokens: {old_max_tokens} → {agent.max_tokens}")
                if old_context != agent.context_window_tokens:
                    print(f"  - context_window: {old_context} → {agent.context_window_tokens}")
                updated_count += 1
                print()
            else:
                print(f"  {agent.name}: Already OK\n")
        
        await session.commit()
        print(f"\n✓ Updated {updated_count} agents successfully!")
        print(f"\nNote: The monitoring service will continue to track and auto-update")
        print(f"agent capabilities every 30 seconds while the backend is running.")


if __name__ == "__main__":
    asyncio.run(update_agents())
