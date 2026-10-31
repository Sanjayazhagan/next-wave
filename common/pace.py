"""Spaces LLM calls so this process stays under the provider's per-minute limits.

Core and the modules share one instance. Each call books the next free slot, and
waits longer only when the last minute's tokens would pass the limit, so short
bursts run at full speed. LLM_RPM=0 and LLM_TPM=0 turn it off.
"""
from __future__ import annotations

import threading
import time

from .config import env

CHARS_PER_TOKEN = 4
IMAGE_TOKENS = 2500
WINDOW = 60.0

_lock = threading.Lock()
_next_slot = 0.0
_booked: list[tuple[float, int]] = []


def _limit(name: str, default: int) -> int:
    try:
        return max(int(env(name, str(default))), 0)
    except ValueError:
        return default


def estimate_tokens(messages: list[dict], reply_tokens: int) -> int:
    total = reply_tokens
    for message in messages:
        content = message["content"]
        parts = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for part in parts:
            total += len(part["text"]) // CHARS_PER_TOKEN if part["type"] == "text" else IMAGE_TOKENS
    return total


def book(tokens: int) -> float:
    """Reserves the next slot and returns how many seconds to wait for it."""
    global _next_slot
    rpm, tpm = _limit("LLM_RPM", 30), _limit("LLM_TPM", 7000)
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        recent = [entry for entry in _booked if entry[0] > now - WINDOW]
        if tpm:
            # A call waits only once the last minute's bookings would pass the limit.
            for booked_at, _ in recent:
                if sum(t for at, t in recent if at > slot - WINDOW) + tokens <= tpm:
                    break
                slot = max(slot, booked_at + WINDOW)
        recent.append((slot, tokens))
        _booked[:] = recent
        _next_slot = slot + (WINDOW / rpm if rpm else 0)
    return slot - now
