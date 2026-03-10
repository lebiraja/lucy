"""Routing and ranking nodes for dynamic strategy and council review aggregation.

Direct ports of orchestrator._extract_json(), parse_ranking_from_text(),
and calculate_aggregate_rankings().
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import List

from app.services.langgraph.state import AgentResult, RankingResult


def extract_json(text: str) -> str:
    """Strip markdown code fences (```json ... ``` or ``` ... ```) and return raw JSON.

    Direct port of orchestrator._extract_json().
    """
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def parse_ranking_from_text(text: str, valid_labels: list[str]) -> List[str]:
    """Extract ordered ranking labels from LLM output.

    Priority:
      1. FINAL RANKING: section with numbered list  → most reliable
      2. FINAL RANKING: section without numbers     → labels in order
      3. Full text scan for Response X patterns     → last resort
      4. Returns [] on complete failure

    Direct port of orchestrator.parse_ranking_from_text().
    """
    if "FINAL RANKING:" in text:
        section = text.split("FINAL RANKING:", 1)[1]
        # Primary: numbered list "1. Response A"
        numbered = re.findall(r'\d+\.\s*(Response [A-Z])', section)
        if numbered:
            return [r for r in numbered if r in valid_labels]
        # Fallback 1: any "Response X" in section order
        found = re.findall(r'Response [A-Z]', section)
        return [r for r in found if r in valid_labels]
    # Fallback 2: scan full text
    found = re.findall(r'Response [A-Z]', text)
    return [r for r in found if r in valid_labels]


def calculate_aggregate_rankings(
    reviews: list[dict],
    label_to_agent_id: dict[str, int],
    label_to_agent_info: dict[str, dict],
) -> list[dict]:
    """Aggregate peer rankings into a leaderboard.

    Average rank position per agent (1 = best). Lower average = better.

    Adapted from orchestrator.calculate_aggregate_rankings() to work with
    serialized dicts instead of ORM Agent objects.
    """
    valid_labels = list(label_to_agent_id.keys())
    agent_positions: dict[int, list[int]] = defaultdict(list)

    for review in reviews:
        parsed = parse_ranking_from_text(review["response"], valid_labels)
        for position, label in enumerate(parsed, start=1):
            agent_id = label_to_agent_id.get(label)
            if agent_id is not None:
                agent_positions[agent_id].append(position)

    aggregate = []
    for label, agent_id in label_to_agent_id.items():
        info = label_to_agent_info.get(label, {})
        positions = agent_positions.get(agent_id, [])
        if positions:
            aggregate.append({
                "agent_id": agent_id,
                "agent_name": info.get("name", "unknown"),
                "agent_role": info.get("role", "employee"),
                "average_rank": round(sum(positions) / len(positions), 2),
                "rankings_count": len(positions),
                "label": label,
            })

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate
