"""Web search tool using SerpAPI (serpapi.com)."""

from __future__ import annotations
import re
import httpx
from app.config import get_settings


async def web_search(args: dict, workspace_dir: str) -> dict:
    """Search Google via SerpAPI. Returns top 5 results."""
    query = args.get("query", "")
    if not query:
        return {"error": "query is required"}

    settings = get_settings()
    if not settings.serper_api_key:
        return {"error": "SERPER_API_KEY not configured"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": settings.serper_api_key,
                    "engine": "google",
                    "num": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic_results", [])[:5]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": _strip_html(item.get("snippet", "")),
            })

        answer_box = None
        if "answer_box" in data:
            ab = data["answer_box"]
            answer_box = ab.get("answer") or ab.get("snippet") or ab.get("title")

        knowledge_graph = None
        if "knowledge_graph" in data:
            kg = data["knowledge_graph"]
            knowledge_graph = kg.get("description") or kg.get("title")

        return {
            "query": query,
            "answer_box": answer_box,
            "knowledge_graph": knowledge_graph,
            "results": results,
        }

    except httpx.HTTPError as e:
        return {"error": f"Search request failed: {str(e)}"}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)
