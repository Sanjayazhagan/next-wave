"""FastAPI app for the language service. Request and response shapes follow contracts/language.py.

Run: uvicorn modules.language.app:app --host 0.0.0.0 --port 8081
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from contracts.language import SttRequest, SttResponse, TranslateRequest, TranslateResponse, TtsRequest, TtsResponse

from .audio import AudioError, to_wav16k
from .providers.bhashini import Bhashini
from .providers.sarvam import Sarvam
from .router import AllProvidersFailed, Router

load_dotenv()
log = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 10_000_000


# Optional extras on top of the shared contract. Core sends only the contract fields.
class SttIn(SttRequest):
    language: str | None = None      # hint; omit to auto-detect


class SttOut(SttResponse):
    provider: str
    latency_ms: int


class TranslateIn(TranslateRequest):
    keep: list[str] = []             # terms to keep as-is, e.g. scheme names


class TranslateOut(TranslateResponse):
    provider: str
    latency_ms: int


class TtsIn(TtsRequest):
    voice: str | None = None


class TtsOut(TtsResponse):
    provider: str
    latency_ms: int


def _log(op: str, provider: str | None, latency_ms: int | None, ok: bool, input_len: int, request_id: str) -> None:
    """One line per request. Never the text or audio itself."""
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "language.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "request_id": request_id, "op": op,
                            "provider": provider, "latency_ms": latency_ms, "ok": ok, "input_len": input_len}) + "\n")


def create_app(router: Router | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient() as http:
            app.state.router = router or Router({"bhashini": Bhashini(http), "sarvam": Sarvam(http)})
            yield

    app = FastAPI(title="GradientZero language service", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    def fail(op: str, exc: AllProvidersFailed, rid: str, n: int) -> HTTPException:
        _log(op, None, None, False, n, rid)
        return HTTPException(503, detail={"op": op, "errors": exc.errors})

    @app.post("/stt", response_model=SttOut)
    async def stt(body: SttIn, request: Request) -> SttOut:
        rid = request.state.request_id
        try:
            audio = base64.b64decode(body.audio_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "audio_base64 is not valid base64") from None
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413 if audio else 400, "audio is empty or too large")
        try:
            wav = to_wav16k(audio)
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from None
        try:
            (text, lang), provider, ms = await request.app.state.router.run(
                "stt", lambda p: p.stt(wav, body.language))
        except AllProvidersFailed as exc:
            raise fail("stt", exc, rid, len(audio)) from None
        _log("stt", provider, ms, True, len(audio), rid)
        return SttOut(text=text, language=lang, provider=provider, latency_ms=ms)

    @app.post("/translate", response_model=TranslateOut)
    async def translate(body: TranslateIn, request: Request) -> TranslateOut:
        rid = request.state.request_id
        if body.source == body.target or not body.text.strip():
            return TranslateOut(text=body.text, provider="none", latency_ms=0)
        try:
            text, provider, ms = await request.app.state.router.translate(body.text, body.source, body.target, body.keep)
        except AllProvidersFailed as exc:
            raise fail("translate", exc, rid, len(body.text)) from None
        _log("translate", provider, ms, True, len(body.text), rid)
        return TranslateOut(text=text, provider=provider, latency_ms=ms)

    @app.post("/tts", response_model=TtsOut)
    async def tts(body: TtsIn, request: Request) -> TtsOut:
        rid = request.state.request_id
        if not body.text.strip():
            raise HTTPException(400, "text is empty")
        try:
            (audio, mime), provider, ms = await request.app.state.router.run(
                "tts", lambda p: p.tts(body.text, body.language, body.voice))
        except AllProvidersFailed as exc:
            raise fail("tts", exc, rid, len(body.text)) from None
        _log("tts", provider, ms, True, len(body.text), rid)
        # Core converts this to OGG/Opus for voice notes (app/language.py).
        return TtsOut(audio_base64=base64.b64encode(audio).decode(), mime_type=mime, provider=provider, latency_ms=ms)

    @app.get("/health")
    async def health(request: Request) -> dict:
        r: Router = request.app.state.router
        return {name: {"configured": p.configured(), "ok": r.health.get(name).ok if name in r.health else None,
                       "last_latency_ms": r.health[name].last_latency_ms if name in r.health else None}
                for name, p in r.providers.items()}

    return app


app = create_app()
