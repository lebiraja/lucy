"""OpenAI-compatible vLLM client for communicating with LLM agents."""

import time
import httpx
from app.models import Agent
from app.config import get_settings

settings = get_settings()

# Module-level shared client — initialized in app lifespan (main.py).
# Using a single AsyncClient enables connection pooling across parallel agent calls.
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx client. Falls back to a new client if not initialized (e.g. tests)."""
    if _http_client is not None:
        return _http_client
    return httpx.AsyncClient(timeout=settings.llm_request_timeout)


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

    # If model_name is not set, try to detect it
    model_name = agent.model_name
    if not model_name:
        try:
            info = await fetch_model_info(agent.endpoint)
            model_name = info["model_name"]
        except Exception as e:
            raise Exception(
                f"Agent '{agent.name}' has no model_name set and endpoint probe failed: {e}"
            )

    # Context window: use agent.context_window_tokens if available, else default 4096
    context_window = getattr(agent, 'context_window_tokens', None) or 4096
    effective_max_output = min(agent.max_tokens, context_window // 2)
    max_input_tokens = max(context_window - effective_max_output - 100, 200)  # 100 token buffer
    max_input_chars = int(max_input_tokens * 3.5)  # ~3.5 chars per token

    processed_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > max_input_chars:
            content = content[:max_input_chars] + "\n\n[...TRUNCATED DUE TO CONTEXT LIMIT...]"
        processed_messages.append({"role": msg.get("role"), "content": content})

    payload = {
        "model": model_name,
        "messages": processed_messages,
        "temperature": temperature if temperature is not None else agent.temperature,
        "max_tokens": max_tokens if max_tokens is not None else effective_max_output,
        "top_p": top_p if top_p is not None else agent.top_p,
        "stream": False,
    }

    start = time.perf_counter()
    client = _get_client()

    response = await client.post(url, json=payload)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_details = exc.response.text
        try:
            error_details = exc.response.json()
        except Exception:
            pass
        raise Exception(
            f"Client error '{exc.response.status_code}' for url '{exc.request.url}'. Details: {error_details}"
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    data = response.json()

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
        client = httpx.AsyncClient(timeout=settings.health_check_timeout)
        async with client:
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
    first = models[0]
    model_id = first.get("id", "unknown")

    # vLLM exposes max_model_len in the model object
    max_model_len: int | None = None
    raw = first.get("max_model_len") or first.get("max_context_length")
    if raw is not None:
        try:
            max_model_len = int(raw)
        except (TypeError, ValueError):
            pass

    result: dict = {
        "model_name": model_id,
        "models": [m.get("id") for m in models],
    }
    if max_model_len is not None:
        result["max_model_len"] = max_model_len
        # Recommend max_tokens as 25% of context window, capped at 4096
        result["recommended_max_tokens"] = min(max_model_len // 4, 4096)
    return result

