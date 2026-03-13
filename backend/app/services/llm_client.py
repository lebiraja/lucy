"""OpenAI-compatible vLLM client for communicating with LLM agents."""

import time
import json
import httpx
from typing import AsyncIterator
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
        except Exception:
            model_name = "default"

    # Context window: prefer agent setting, but verify with endpoint if possible.
    context_window = getattr(agent, 'context_window_tokens', None) or 4096
    endpoint_context = None
    try:
        info = await fetch_model_info(agent.endpoint)
        endpoint_context = info.get('context_window') or info.get('max_model_len')
    except Exception:
        endpoint_context = None

    if endpoint_context:
        try:
            endpoint_context = int(endpoint_context)
            context_window = min(context_window, endpoint_context)
        except Exception:
            pass

    try:
        context_window = int(context_window)
    except Exception:
        context_window = 4096

    # First, calculate how many tokens the input text actually uses (roughly)
    # Reserve at least 60% of context for input, minimum 512 tokens
    max_input_tokens = max(int(context_window * 0.6), 512)
    max_input_chars = int(max_input_tokens * 3.5)
    
    processed_messages = []
    estimated_input_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            if len(content) > max_input_chars:
                content = content[:max_input_chars] + "\n\n[...TRUNCATED DUE TO CONTEXT LIMIT...]"
            estimated_input_chars += len(content)
        processed_messages.append({"role": msg.get("role"), "content": content})

    # Estimate input tokens used
    estimated_input_tokens = int(estimated_input_chars / 3.5) + 100 # Add 100 for formatting overhead
    
    # Calculate how many tokens we have left in the context window
    # Reserve at least 20% of context for output, minimum 256 tokens
    max_output_tokens = max(int(context_window * 0.4), 256)
    remaining_tokens = max(context_window - estimated_input_tokens, 256)
    
    # The max output is the minimum of: requested, remaining space, and 40% of context
    requested_max_tokens = max_tokens if max_tokens is not None else agent.max_tokens
    effective_max_output = min(requested_max_tokens, remaining_tokens, max_output_tokens)

    payload = {
        "model": model_name,
        "messages": processed_messages,
        "temperature": temperature if temperature is not None else agent.temperature,
        "max_tokens": effective_max_output,
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
        err_msg = ""
        try:
            parsed = exc.response.json()
            error_details = parsed
            err_msg = parsed.get("error", {}).get("message", "") if isinstance(parsed, dict) else str(parsed)
        except Exception:
            err_msg = str(error_details)

        # Retry logic for token limit errors (model context / input length oversize)
        if exc.response.status_code == 400 and ("maximum input length" in err_msg.lower() or "requested" in err_msg.lower() and "context length" in err_msg.lower()):
            fallback_max = max(64, min(512, int(context_window * 0.2)))
            payload["max_tokens"] = fallback_max
            payload["messages"] = [
                {"role": m["role"], "content": (m["content"][:int(max_input_chars*0.4)] + "\n\n[...TRUNCATED...]") if isinstance(m.get("content"), str) and len(m.get("content", "")) > int(max_input_chars*0.4) else m.get("content")}
                for m in processed_messages
            ]
            res_retry = await client.post(url, json=payload)
            try:
                res_retry.raise_for_status()
            except httpx.HTTPStatusError as exc2:
                raise Exception(
                    f"Model retry failed '{exc2.response.status_code}' for url '{exc2.request.url}'. Details: {exc2.response.text}"
                )
            duration_ms = int((time.perf_counter() - start) * 1000)
            data = res_retry.json()
            content = data["choices"][0]["message"]["content"]
            return content, duration_ms

        raise Exception(
            f"Client error '{exc.response.status_code}' for url '{exc.request.url}'. Details: {error_details}"
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    return content, duration_ms


async def chat_completion_stream(
    agent: Agent,
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
) -> AsyncIterator[dict]:
    """
    Send a streaming chat completion request to a vLLM agent.

    Args:
        agent: The Agent ORM instance with endpoint and model config.
        messages: List of message dicts [{"role": "...", "content": "..."}].
        temperature: Override agent's default temperature.
        max_tokens: Override agent's default max_tokens.
        top_p: Override agent's default top_p.

    Yields:
        Dict with {
            "content": str (chunk of text),
            "done": bool (true on last chunk),
            "duration_ms": int (only on last chunk)
        }

    Raises:
        Exception: If the vLLM endpoint returns an error or is unreachable.
    """
    url = f"{agent.endpoint.rstrip('/')}/v1/chat/completions"

    # If model_name is not set, try to detect it
    model_name = agent.model_name
    if not model_name:
        try:
            info = await fetch_model_info(agent.endpoint)
            model_name = info["model_name"]
        except Exception:
            model_name = "default"

    # Context window: prefer agent setting, but verify with endpoint if possible.
    context_window = getattr(agent, 'context_window_tokens', None) or 4096
    endpoint_context = None
    try:
        info = await fetch_model_info(agent.endpoint)
        endpoint_context = info.get('context_window') or info.get('max_model_len')
    except Exception:
        endpoint_context = None

    if endpoint_context:
        try:
            endpoint_context = int(endpoint_context)
            context_window = min(context_window, endpoint_context)
        except Exception:
            pass

    try:
        context_window = int(context_window)
    except Exception:
        context_window = 4096

    # Reserve at least 60% of context for input, minimum 512 tokens
    max_input_tokens = max(int(context_window * 0.6), 512)
    max_input_chars = int(max_input_tokens * 3.5)
    
    processed_messages = []
    estimated_input_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            if len(content) > max_input_chars:
                content = content[:max_input_chars] + "\n\n[...TRUNCATED DUE TO CONTEXT LIMIT...]"
            estimated_input_chars += len(content)
        processed_messages.append({"role": msg.get("role"), "content": content})

    # Estimate input tokens used
    estimated_input_tokens = int(estimated_input_chars / 3.5) + 100
    
    # Calculate max output tokens
    max_output_tokens = max(int(context_window * 0.4), 256)
    remaining_tokens = max(context_window - estimated_input_tokens, 256)
    
    requested_max_tokens = max_tokens if max_tokens is not None else agent.max_tokens
    effective_max_output = min(requested_max_tokens, remaining_tokens, max_output_tokens)

    payload = {
        "model": model_name,
        "messages": processed_messages,
        "temperature": temperature if temperature is not None else agent.temperature,
        "max_tokens": effective_max_output,
        "top_p": top_p if top_p is not None else agent.top_p,
        "stream": True,  # Enable streaming
    }

    start = time.perf_counter()
    client = _get_client()

    try:
        async with client.stream("POST", url, json=payload) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                error_details = exc.response.text if hasattr(exc.response, 'text') else str(exc)
                try:
                    await response.aread()
                    error_details = exc.response.json()
                except Exception:
                    pass
                raise Exception(
                    f"Client error '{exc.response.status_code}' for url '{exc.request.url}'. Details: {error_details}"
                )

            full_content = ""
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                
                # SSE format: "data: {...}"
                if line.startswith("data: "):
                    line = line[6:]  # Remove "data: " prefix
                
                if line.strip() == "[DONE]":
                    break
                
                try:
                    chunk_data = json.loads(line)
                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    
                    if content:
                        full_content += content
                        yield {
                            "content": content,
                            "done": False,
                            "full_content": full_content,
                        }
                except json.JSONDecodeError:
                    # Skip malformed JSON lines
                    continue

            duration_ms = int((time.perf_counter() - start) * 1000)
            yield {
                "content": "",
                "done": True,
                "full_content": full_content,
                "duration_ms": duration_ms,
            }

    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        # Even on error, yield final message with error info
        yield {
            "content": "",
            "done": True,
            "error": str(e),
            "duration_ms": duration_ms,
        }


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
    Fetch detailed model information from a vLLM endpoint via /v1/models.

    Returns:
        Dict with 'model_name', 'context_window', 'max_model_len' and other info,
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
    model_data = models[0]
    model_id = model_data.get("id", "unknown")
    
    # Extract context window from vLLM model metadata
    # vLLM exposes max_model_len in the model data
    max_model_len = model_data.get("max_model_len")
    
    # If not in model data, try to infer from common model patterns
    if not max_model_len:
        if any(x in model_id.lower() for x in ["qwen3-4b", "gemma-3-4b", "phi-2"]):
            max_model_len = 2048
        elif any(x in model_id.lower() for x in ["ministral", "mistral-7b"]):
            max_model_len = 8192
        elif "llama-3" in model_id.lower():
            max_model_len = 8192
        elif "gpt" in model_id.lower():
            max_model_len = 16384
        else:
            max_model_len = 4096  # Safe default
    
    return {
        "model_name": model_id,
        "context_window": max_model_len,
        "max_model_len": max_model_len,
        "models": [m.get("id") for m in models],
        "raw_data": model_data,  # Store full metadata for debugging
    }

