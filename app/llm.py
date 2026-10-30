"""OpenAI-compatible chat client. In production this talks to freellmpool."""
import json
import logging
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 60


class LlmError(Exception):
    pass


def parse_json_object(text: str) -> dict[str, Any]:
    """Free models often wrap JSON in prose or code fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LlmError("Model reply held no JSON object")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmError("Model reply was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LlmError("Model reply was not a JSON object")
    return parsed


class ChatLlm:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        self._key = settings.llm_api_key
        self._model = settings.llm_model
        self._configured = bool(settings.llm_base_url)

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._configured:
            raise LlmError("LLM_BASE_URL is not set")
        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                return parse_json_object(await self._complete(system, user))
            except (LlmError, httpx.HTTPError) as exc:
                last_error = exc
                log.warning("LLM attempt failed: %s", type(exc).__name__)
        raise LlmError(f"LLM failed after {MAX_ATTEMPTS} attempts") from last_error

    async def _complete(self, system: str, user: str) -> str:
        response = await self._http.post(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "temperature": 0,
                "max_tokens": 600,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("Unexpected LLM response shape") from exc
        if not content:
            raise LlmError("Model returned no text")
        return content
