"""OpenAI-compatible vLLM client for communicating with LLM agents."""

import time
import httpx
from app.models import Agent
from app.config import get_settings

settings = get_settings()


async def chat_completion(
    agent: Agent,
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> tuple[str, int]:
    """
    Send a chat completion request to a vLLM agent.

    Args:
        agent: The Agent ORM instance with endpoint and model config.
        messages: List of message dicts [{"role": "...", "content": "..."}].
        temperature: Override agent's default temperature.
        max_tokens: Override agent's default max_tokens.
        top_p: Override agent's default top_p.

    Returns:
        Tuple of (response_text, duration_ms).

    Raises:
        httpx.HTTPStatusError: If the vLLM endpoint returns an error.
        httpx.ConnectError: If the endpoint is unreachable.
    """
    url = f"{agent.endpoint.rstrip('/')}/v1/chat/completions"

    payload = {
        "model": agent.model_name,
        "messages": messages,
        "temperature": temperature if temperature is not None else agent.temperature,
        "max_tokens": max_tokens if max_tokens is not None else agent.max_tokens,
        "top_p": top_p if top_p is not None else agent.top_p,
        "stream": False,
    }

    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=settings.llm_request_timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

    duration_ms = int((time.perf_counter() - start) * 1000)
    data = response.json()

    # Extract the assistant's reply
    content = data["choices"][0]["message"]["content"]
    return content, duration_ms


async def check_health(endpoint: str) -> tuple[bool, float | None, str | None]:
    """
    Check if a vLLM endpoint is reachable by hitting /v1/models.

    Returns:
        Tuple of (is_online, latency_ms, error_message).
    """
    url = f"{endpoint.rstrip('/')}/v1/models"

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=settings.health_check_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return True, latency_ms, None
    except httpx.ConnectError:
        return False, None, "Connection refused — endpoint unreachable"
    except httpx.TimeoutException:
        return False, None, "Timeout — endpoint did not respond"
    except httpx.HTTPStatusError as e:
        return False, None, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, None, str(e)


async def fetch_model_info(endpoint: str) -> dict:
    """
    Fetch model information from a vLLM endpoint via /v1/models.

    Returns:
        Dict with 'model_name' and optionally other info,
        or raises an exception if the endpoint is unreachable.
    """
    url = f"{endpoint.rstrip('/')}/v1/models"

    async with httpx.AsyncClient(timeout=settings.health_check_timeout) as client:
        response = await client.get(url)
        response.raise_for_status()

    data = response.json()
    models = data.get("data", [])

    if not models:
        raise ValueError("No models found at this endpoint")

    # vLLM typically serves one model per endpoint
    model_id = models[0].get("id", "unknown")
    return {
        "model_name": model_id,
        "models": [m.get("id") for m in models],
    }

