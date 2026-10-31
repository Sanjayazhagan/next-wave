"""Provider interface: every provider speaks ISO 639-1 codes and WAV audio."""
from __future__ import annotations

from typing import Protocol

from common.config import env


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def configured(self) -> bool: ...

    async def stt(self, wav: bytes, lang: str | None) -> tuple[str, str]:
        """Return (transcript, detected ISO language). `lang` None means auto-detect."""

    async def translate(self, text: str, src: str, tgt: str) -> str: ...

    async def tts(self, text: str, lang: str, voice: str | None) -> tuple[bytes, str]:
        """Return (audio bytes, mime type)."""


def timeout_s(op: str) -> float:
    """Speech-to-text gets longer than the other calls: a 20-second voice note takes a few seconds."""
    if op == "stt":
        return float(env("STT_TIMEOUT_S", "15"))
    return float(env("PROVIDER_TIMEOUT_S", "5"))
