from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class AzureOpenAIError(RuntimeError):
    """Raised when Azure OpenAI chat completion fails."""


def _build_url(endpoint: str, deployment: str, api_version: str) -> str:
    endpoint = endpoint.rstrip('/')
    return f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"


async def chat_completion(
    messages: List[Dict[str, str]],
    *,
    endpoint: str,
    api_key: str,
    deployment: str,
    api_version: str,
    temperature: float = 0.0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    if not messages:
        raise AzureOpenAIError("messages must contain at least one entry")

    url = _build_url(endpoint, deployment, api_version)
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        raise AzureOpenAIError(
            f"Azure OpenAI request failed ({response.status_code}): {response.text}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AzureOpenAIError("Azure OpenAI response was not valid JSON") from exc

    try:
        choices = body["choices"]
        if not isinstance(choices, list) or not choices:
            raise KeyError
        message = choices[0]["message"]
        content = message.get("content")
    except (KeyError, TypeError) as exc:
        raise AzureOpenAIError("Azure OpenAI response missing assistant message content") from exc

    if isinstance(content, list):
        fragments = [fragment.get("text", "") for fragment in content if isinstance(fragment, dict)]
        return "".join(fragments)
    if isinstance(content, str):
        return content
    raise AzureOpenAIError("Assistant message content was not a string")
