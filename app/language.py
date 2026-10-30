"""HTTP client for the language service. See contracts/language.py."""
import asyncio
import base64
import logging
import subprocess

import httpx

from app.config import Settings
from contracts.language import (
    SttRequest,
    SttResponse,
    TranslateRequest,
    TranslateResponse,
    TtsRequest,
    TtsResponse,
)

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


class LanguageError(Exception):
    pass


class LanguageService:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = settings.language_service_url.rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._base)

    async def _post(self, path: str, body: dict) -> dict:
        try:
            response = await self._http.post(
                f"{self._base}{path}", json=body, timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LanguageError(f"{path} failed: {type(exc).__name__}") from exc
        return response.json()

    async def speech_to_text(self, audio: bytes, mime_type: str) -> SttResponse:
        request = SttRequest(
            audio_base64=base64.b64encode(audio).decode(), mime_type=mime_type
        )
        return SttResponse.model_validate(await self._post("/stt", request.model_dump()))

    async def translate(self, text: str, source: str, target: str) -> str:
        """Fall back to the original text, so a language outage stops nothing."""
        if not self.available or source == target:
            return text
        request = TranslateRequest(text=text, source=source, target=target)
        try:
            reply = await self._post("/translate", request.model_dump())
        except LanguageError as exc:
            log.warning("Translation skipped: %s", exc)
            return text
        return TranslateResponse.model_validate(reply).text

    async def text_to_speech(self, text: str, language: str) -> bytes:
        request = TtsRequest(text=text, language=language)
        reply = TtsResponse.model_validate(await self._post("/tts", request.model_dump()))
        return base64.b64decode(reply.audio_base64)


def _to_voice_note(audio: bytes) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-i", "pipe:0",
            "-vn", "-ac", "1", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
        ],
        input=audio,
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise LanguageError("ffmpeg could not convert the audio")
    return result.stdout


async def to_voice_note(audio: bytes) -> bytes:
    """Convert any audio to OGG/Opus, the only format WhatsApp plays as a voice note."""
    return await asyncio.to_thread(_to_voice_note, audio)
