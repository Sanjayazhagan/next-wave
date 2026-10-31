"""OpenAI-compatible chat client, for Groq or the freellmpool proxy."""
import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import Settings
from common.pace import book, estimate_tokens

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 60
DEFAULT_RATE_LIMIT_WAIT = 2.0
MAX_RATE_LIMIT_WAIT = 20.0
MAX_REPLY_TOKENS = 600


class LlmError(Exception):
    pass


def _rate_limit_wait(exc: Exception) -> float:
    """Seconds to wait before retrying. Free tiers limit requests per minute."""
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 429:
        return 0
    try:
        wait = float(exc.response.headers.get("retry-after", DEFAULT_RATE_LIMIT_WAIT))
    except ValueError:
        wait = DEFAULT_RATE_LIMIT_WAIT
    return min(wait, MAX_RATE_LIMIT_WAIT)


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
        self.configured = bool(settings.llm_base_url)

    async def complete_json(
        self,
        system: str,
        user: str,
        attempts: int = MAX_ATTEMPTS,
        timeout: float = TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if not self.configured:
            raise LlmError("LLM_BASE_URL is not set")
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return parse_json_object(await self._complete(system, user, timeout))
            except (LlmError, httpx.HTTPError) as exc:
                last_error = exc
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else ""
                log.warning("LLM attempt failed: %s %s", type(exc).__name__, status)
                await asyncio.sleep(_rate_limit_wait(exc))
        raise LlmError(f"LLM failed after {attempts} attempts") from last_error

    async def _complete(self, system: str, user: str, timeout: float) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        await asyncio.sleep(book(estimate_tokens(messages, MAX_REPLY_TOKENS)))
        response = await self._http.post(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "temperature": 0,
                "max_tokens": MAX_REPLY_TOKENS,
                "messages": messages,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("Unexpected LLM response shape") from exc
        if not content:
            raise LlmError("Model returned no text")
        return content
