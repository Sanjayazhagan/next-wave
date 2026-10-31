"""Sarvam AI: Saaras speech-to-text, Sarvam-Translate, Bulbul text-to-speech.

API reference (checked 31 Oct 2026): https://docs.sarvam.ai/api-reference/introduction
"""
from __future__ import annotations

import base64
import os

import httpx

from ..langcodes import SARVAM_TTS, from_sarvam, to_sarvam
from .base import ProviderError, timeout_s

BASE = "https://api.sarvam.ai"


class Sarvam:
    name = "sarvam"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @staticmethod
    def _key() -> str:
        return os.getenv("SARVAM_API_KEY", "")

    def configured(self) -> bool:
        return bool(self._key())

    async def _call(self, op: str, path: str, **kwargs) -> dict:
        try:
            r = await self._http.post(f"{BASE}{path}", headers={"api-subscription-key": self._key()},
                                      timeout=timeout_s(op), **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"sarvam {op}: {type(exc).__name__}") from exc
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise ProviderError(f"sarvam {op}: HTTP {r.status_code} {msg[:200]}")
        return r.json()

    async def stt(self, wav: bytes, lang: str | None) -> tuple[str, str]:
        data = {"model": os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
                "language_code": to_sarvam(lang) if lang else "unknown"}
        if mode := os.getenv("SARVAM_STT_MODE", ""):   # e.g. codemix, for Tamil-English speech
            data["mode"] = mode
        body = await self._call("stt", "/speech-to-text", data=data, files={"file": ("audio.wav", wav, "audio/wav")})
        detected = from_sarvam(body.get("language_code")) or lang
        if not detected:
            raise ProviderError("sarvam stt: no language detected")
        return body.get("transcript", ""), detected

    async def translate(self, text: str, src: str, tgt: str) -> str:
        body = await self._call("translate", "/translate", json={
            "input": text, "source_language_code": to_sarvam(src), "target_language_code": to_sarvam(tgt),
            "model": os.getenv("SARVAM_TRANSLATE_MODEL", "sarvam-translate:v1")})
        return body["translated_text"]

    async def tts(self, text: str, lang: str, voice: str | None) -> tuple[bytes, str]:
        if lang not in SARVAM_TTS:
            raise ProviderError(f"sarvam tts: {lang} not supported")
        payload = {"text": text, "language_code": to_sarvam(lang),
                   "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")}
        if speaker := (voice or os.getenv("SARVAM_TTS_SPEAKER", "")):
            payload["speaker"] = speaker
        body = await self._call("tts", "/text-to-speech", json=payload)
        audios = body.get("audios") or []
        if not audios:
            raise ProviderError("sarvam tts: no audio returned")
        return base64.b64decode(audios[0]), "audio/wav"
