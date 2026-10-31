"""Single entry point for every LLM call made by the remote modules.

Talks to the same OpenAI-compatible endpoint as core (LLM_BASE_URL, LLM_API_KEY).
Text calls use LLM_MODEL; image calls use VISION_MODEL, which must be a
vision-capable model on that endpoint. Each call is logged as one JSON line to
`$LOG_DIR/llm.jsonl` (model, tokens, latency, caller). Content is never logged.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

T = TypeVar("T", bound=BaseModel)
TIMEOUT_SECONDS = 60

_lock = threading.Lock()
_calls = 0


class LLMError(RuntimeError):
    pass


def llm_calls_total() -> int:
    """Number of LLM calls made by this process (used by the benchmark)."""
    return _calls


def _env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise LLMError(f"{name} is not set; see .env.example")
    return value


def _log(record: dict) -> None:
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    with _lock, open(log_dir / "llm.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _mime(img: bytes) -> str:
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img[:4] == b"RIFF" and img[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _json_object(text: str) -> str:
    """Models often wrap JSON in prose or code fences; keep the outermost object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("model reply held no JSON object")
    return text[start:end + 1]


def _schema_instruction(schema: type[BaseModel]) -> str:
    return ("Reply with one JSON object only, matching this JSON Schema:\n"
            + json.dumps(schema.model_json_schema(), separators=(",", ":")))


def _post(model: str, messages: list[dict]) -> tuple[str, dict]:
    url = f"{_env('LLM_BASE_URL').rstrip('/')}/chat/completions"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'unused')}"},
        json={"model": model, "temperature": 0, "messages": messages,
              "response_format": {"type": "json_object"}},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    body = resp.json()
    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("unexpected LLM response shape") from exc
    return content, body.get("usage") or {}


def _complete(model: str, messages: list[dict], schema: type[T], caller: str) -> T:
    """Call the model and validate against `schema`; on a validation error retry once with the error."""
    global _calls
    attempt_messages = messages
    last_err: Exception | None = None
    for attempt in range(2):
        t0 = time.perf_counter()
        ok, usage = False, {}
        try:
            content, usage = _post(model, attempt_messages)
            parsed = schema.model_validate_json(_json_object(content))
            ok = True
            return parsed
        except (ValidationError, LLMError) as e:
            last_err = e
            # The error text names fields, not document content.
            attempt_messages = messages + [{"role": "user", "content":
                f"Your previous answer was invalid: {str(e)[:1500]}\nReturn corrected JSON only."}]
        except httpx.HTTPError as e:
            raise LLMError(f"{caller}: {type(e).__name__}") from e
        finally:
            with _lock:
                _calls += 1
            _log({"ts": datetime.now(UTC).isoformat(), "caller": caller, "model": model, "attempt": attempt,
                  "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                  "latency_ms": round((time.perf_counter() - t0) * 1000), "ok": ok})
    raise LLMError(f"{caller}: no valid JSON after retry") from last_err


def vision_json(images: list[bytes], prompt: str, schema: type[T], caller: str, system: str | None = None) -> T:
    """Send images + prompt to VISION_MODEL; return a validated `schema` instance."""
    content: list[dict] = [{"type": "text", "text": f"{prompt}\n\n{_schema_instruction(schema)}"}]
    for img in images:
        content.append({"type": "image_url", "image_url": {
            "url": f"data:{_mime(img)};base64,{base64.b64encode(img).decode()}"}})
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    return _complete(_env("VISION_MODEL"), messages, schema, caller)


def text_json(prompt: str, schema: type[T], caller: str, system: str | None = None) -> T:
    """Send a text prompt to LLM_MODEL; return a validated `schema` instance."""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": f"{prompt}\n\n{_schema_instruction(schema)}"}]
    return _complete(_env("LLM_MODEL"), messages, schema, caller)
