"""News search tool using NewsAPI."""

from __future__ import annotations
import httpx
from app.config import get_settings


async def news_search(args: dict, workspace_dir: str) -> dict:
    """Search recent news articles via NewsAPI."""
    query = args.get("query", "")
    days = int(args.get("days", 7))
    if not query:
        return {"error": "query is required"}

    settings = get_settings()
    if not settings.news_api_key:
        return {"error": "NEWS_API_KEY not configured"}

    from datetime import datetime, timezone, timedelta
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "sortBy": "relevancy",
                    "pageSize": 5,
                    "apiKey": settings.news_api_key,
                    "language": "en",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for a in data.get("articles", [])[:5]:
            articles.append({
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "source": a.get("source", {}).get("name", ""),
            })

        return {"query": query, "total_results": data.get("totalResults", 0), "articles": articles}

    except httpx.HTTPError as e:
        return {"error": f"News request failed: {str(e)}"}
