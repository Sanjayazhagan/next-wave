"""Router fallback and the HTTP API, with fake providers (test doubles)."""
import base64

import pytest
from fastapi.testclient import TestClient

from contracts.language import SttResponse, TranslateResponse, TtsResponse
from modules.language import app as app_module
from modules.language.providers.base import ProviderError
from modules.language.router import Router


class Fake:
    def __init__(self, name, fail=False, drop_tokens=False):
        self.name, self.fail, self.drop_tokens, self.calls = name, fail, drop_tokens, 0

    def configured(self):
        return True

    async def stt(self, wav, lang):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} timed out")
        return f"heard by {self.name}", lang or "ta"

    async def translate(self, text, src, tgt):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} down")
        return "translated" if self.drop_tokens else f"[{tgt}] {text}"

    async def tts(self, text, lang, voice):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} down")
        return b"RIFFfake", "audio/wav"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LANG_PRIMARY", "bhashini")
    monkeypatch.delenv("STT_PRIMARY", raising=False)
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "to_wav16k", lambda b: b"wav")


def _client(router):
    return TestClient(app_module.create_app(router))


def test_primary_fails_twice_then_fallback_answers(env):
    bh, sv = Fake("bhashini", fail=True), Fake("sarvam")
    with _client(Router({"bhashini": bh, "sarvam": sv})) as c:
        r = c.post("/stt", json={"audio_base64": base64.b64encode(b"ogg").decode(), "mime_type": "audio/ogg"})
    assert r.status_code == 200
    body = r.json()
    assert SttResponse.model_validate(body).language == "ta"
    assert body["provider"] == "sarvam" and bh.calls == 2 and sv.calls == 1
    assert "x-request-id" in r.headers


def test_stt_primary_override(env, monkeypatch):
    monkeypatch.setenv("STT_PRIMARY", "sarvam")
    router = Router({"bhashini": Fake("bhashini"), "sarvam": Fake("sarvam")})
    assert [p.name for p in router.order("stt")] == ["sarvam", "bhashini"]
    assert [p.name for p in router.order("tts")] == ["bhashini", "sarvam"]


def test_both_fail_gives_503_with_both_errors(env):
    with _client(Router({"bhashini": Fake("bhashini", fail=True), "sarvam": Fake("sarvam", fail=True)})) as c:
        r = c.post("/tts", json={"text": "வணக்கம்", "language": "ta"})
    assert r.status_code == 503
    assert set(r.json()["detail"]["errors"]) == {"bhashini", "sarvam"}


def test_translate_retries_other_provider_when_tokens_dropped(env):
    bh, sv = Fake("bhashini", drop_tokens=True), Fake("sarvam")
    with _client(Router({"bhashini": bh, "sarvam": sv})) as c:
        r = c.post("/translate", json={"text": "Pay ₹2,50,000 by 31/12/2026", "source": "en", "target": "ta",
                                       "keep": []})
    body = r.json()
    assert TranslateResponse.model_validate(body).text == "[ta] Pay ₹2,50,000 by 31/12/2026"
    assert body["provider"] == "sarvam"


def test_translate_falls_back_to_plain_text_when_every_provider_drops_tokens(env):
    class Mangles(Fake):
        async def translate(self, text, src, tgt):
            self.calls += 1
            return "income is 0." if "#0#" in text else f"[{tgt}] {text}"

    with _client(Router({"bhashini": Mangles("bhashini")})) as c:
        r = c.post("/translate", json={"text": "Pay ₹500", "source": "en", "target": "ta"})
    assert r.json()["text"] == "[ta] Pay ₹500"     # never "income is 0." with the amount lost


def test_tts_returns_contract_shape_and_logs_no_text(env, tmp_path):
    with _client(Router({"bhashini": Fake("bhashini")})) as c:
        r = c.post("/tts", json={"text": "secret words", "language": "ta"})
        h = c.get("/health").json()
    out = TtsResponse.model_validate(r.json())
    assert base64.b64decode(out.audio_base64) == b"RIFFfake" and out.mime_type == "audio/wav"
    assert h["bhashini"]["ok"] is True
    assert "secret" not in (tmp_path / "language.jsonl").read_text()


def test_bad_base64_is_400(env):
    with _client(Router({"bhashini": Fake("bhashini")})) as c:
        assert c.post("/stt", json={"audio_base64": "!!", "mime_type": "audio/ogg"}).status_code == 400


def test_core_client_talks_to_service(env):
    """Core's own LanguageService client against this app."""
    import asyncio

    import httpx

    from app.language import LanguageService

    service_app = app_module.create_app(Router({"bhashini": Fake("bhashini")}))

    class S:
        language_service_url = "http://language.test"

    async def go():
        async with service_app.router.lifespan_context(service_app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service_app)) as http:
                svc = LanguageService(S(), http)
                heard = await svc.speech_to_text(b"ogg", "audio/ogg")
                text = await svc.translate("hello", "en", "ta")
                audio = await svc.text_to_speech("hi", "ta")
                return heard, text, audio

    heard, text, audio = asyncio.run(go())
    assert heard.text == "heard by bhashini" and text == "[ta] hello" and audio == b"RIFFfake"
