"""Request shapes sent to Sarvam and Bhashini, checked with httpx.MockTransport (test double)."""
import asyncio
import base64
import json

import httpx
import pytest

from modules.language.providers.bhashini import CONFIG_URL, Bhashini
from modules.language.providers.sarvam import Sarvam


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk")
    monkeypatch.setenv("BHASHINI_USER_ID", "uid")
    monkeypatch.setenv("BHASHINI_ULCA_API_KEY", "ulca")
    monkeypatch.setenv("BHASHINI_PIPELINE_ID", "pid")
    monkeypatch.delenv("SARVAM_STT_MODE", raising=False)


def _run(provider_cls, handler, fn):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await fn(provider_cls(http))
    return asyncio.run(go())


def test_sarvam_stt_auto_detects_language(keys):
    seen = {}

    def handler(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers["api-subscription-key"], req.content
        return httpx.Response(200, json={"transcript": "ஸ்காலர்ஷிப் apply பண்ணணும்", "language_code": "ta-IN"})

    text, lang = _run(Sarvam, handler, lambda p: p.stt(b"RIFF", None))
    assert seen["url"] == "https://api.sarvam.ai/speech-to-text" and seen["key"] == "sk"
    assert b'name="language_code"\r\n\r\nunknown' in seen["body"]
    assert lang == "ta" and "apply" in text


def test_sarvam_translate_and_tts(keys):
    def handler(req):
        body = json.loads(req.content)
        if req.url.path == "/translate":
            assert body["source_language_code"] == "en-IN" and body["target_language_code"] == "od-IN"
            return httpx.Response(200, json={"translated_text": "ok"})
        assert body["language_code"] == "ta-IN" and body["text"] == "hi"
        return httpx.Response(200, json={"audios": [base64.b64encode(b"RIFFx").decode()]})

    assert _run(Sarvam, handler, lambda p: p.translate("x", "en", "or")) == "ok"
    assert _run(Sarvam, handler, lambda p: p.tts("hi", "ta", None)) == (b"RIFFx", "audio/wav")


def test_bhashini_config_then_compute_and_caches_config(keys):
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(str(req.url))
        if str(req.url) == CONFIG_URL:
            assert req.headers["userID"] == "uid" and req.headers["ulcaApiKey"] == "ulca"
            assert body["pipelineRequestConfig"]["pipelineId"] == "pid"
            return httpx.Response(200, json={
                "pipelineResponseConfig": [{"taskType": "translation", "config": [
                    {"serviceId": "svc-ta-en", "language": {"sourceLanguage": "ta", "targetLanguage": "en"}}]}],
                "pipelineInferenceAPIEndPoint": {"callbackUrl": "https://dhruva.test/infer",
                                                 "inferenceApiKey": {"name": "Authorization", "value": "inf"}}})
        assert req.headers["Authorization"] == "inf"
        task = body["pipelineTasks"][0]
        assert task["config"]["serviceId"] == "svc-ta-en" and body["inputData"]["input"][0]["source"] == "வணக்கம்"
        return httpx.Response(200, json={"pipelineResponse": [{"output": [{"source": "வணக்கம்", "target": "Hello"}]}]})

    async def twice(p):
        return [await p.translate("வணக்கம்", "ta", "en"), await p.translate("வணக்கம்", "ta", "en")]

    assert _run(Bhashini, handler, twice) == ["Hello", "Hello"]
    assert calls.count(CONFIG_URL) == 1
