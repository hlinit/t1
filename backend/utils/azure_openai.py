from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


class AzureOpenAIError(RuntimeError):
    """Raised when Azure OpenAI returns an error or malformed response."""


@dataclass
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    api_version: str
    deployment: str
    timeout_seconds: float = 60.0


async def chat_completion(
    *,
    config: AzureOpenAIConfig,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    response_format: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call Azure OpenAI chat completions endpoint and return the JSON response."""

    if not messages:
        raise AzureOpenAIError("At least one message is required for chat completion")

    base_url = config.endpoint.rstrip("/")
    url = f"{base_url}/openai/deployments/{config.deployment}/chat/completions?api-version={config.api_version}"

    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    if extra_body:
        payload.update(extra_body)

    headers = {
        "Content-Type": "application/json",
        "api-key": config.api_key,
    }

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        raise AzureOpenAIError(
            f"Azure OpenAI request failed ({response.status_code}): {response.text}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AzureOpenAIError("Azure OpenAI response was not valid JSON") from exc

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AzureOpenAIError("Azure OpenAI response missing choices")

    return body
