"""Bhashini (ULCA): a pipeline config call, then a compute call.

API reference (checked 31 Oct 2026): https://bhashini.gitbook.io/bhashini-apis/
Config returns the compute URL (`callbackUrl`), the inference key header, and a
serviceId per task; it is cached per (task, src, tgt) for an hour.
"""
from __future__ import annotations

import base64
import time

import httpx

from common.config import env

from .base import ProviderError, timeout_s

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
CONFIG_TTL_S = 3600


class Bhashini:
    name = "bhashini"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._cache: dict[tuple, tuple[float, dict]] = {}

    def configured(self) -> bool:
        return all(env(k) for k in ("BHASHINI_USER_ID", "BHASHINI_ULCA_API_KEY", "BHASHINI_PIPELINE_ID"))

    async def _config(self, task: str, src: str, tgt: str | None) -> dict:
        key = (task, src, tgt)
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CONFIG_TTL_S:
            return hit[1]
        language = {"sourceLanguage": src, **({"targetLanguage": tgt} if tgt else {})}
        body = {"pipelineTasks": [{"taskType": task, "config": {"language": language}}],
                "pipelineRequestConfig": {"pipelineId": env("BHASHINI_PIPELINE_ID")}}
        headers = {"userID": env("BHASHINI_USER_ID", ""), "ulcaApiKey": env("BHASHINI_ULCA_API_KEY", "")}
        try:
            r = await self._http.post(CONFIG_URL, json=body, headers=headers, timeout=timeout_s(task))
            r.raise_for_status()
            data = r.json()
            endpoint = data["pipelineInferenceAPIEndPoint"]
            configs = data["pipelineResponseConfig"][0]["config"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"bhashini config {task}: {type(exc).__name__}") from exc
        if not configs:
            raise ProviderError(f"bhashini config {task}: no service for {src}->{tgt}")
        match = next((c for c in configs if c.get("language", {}).get("sourceLanguage") == src
                      and (tgt is None or c.get("language", {}).get("targetLanguage") == tgt)), configs[0])
        result = {"url": endpoint["callbackUrl"], "auth_name": endpoint["inferenceApiKey"]["name"],
                  "auth_value": endpoint["inferenceApiKey"]["value"], "service_id": match["serviceId"]}
        self._cache[key] = (time.monotonic(), result)
        return result

    async def _compute(self, task: str, src: str, tgt: str | None, extra_config: dict, input_data: dict) -> dict:
        cfg = await self._config(task, src, tgt)
        language = {"sourceLanguage": src, **({"targetLanguage": tgt} if tgt else {})}
        body = {"pipelineTasks": [{"taskType": task, "config": {"language": language, "serviceId": cfg["service_id"],
                                                                 **extra_config}}],
                "inputData": input_data}
        try:
            r = await self._http.post(cfg["url"], json=body, headers={cfg["auth_name"]: cfg["auth_value"]},
                                      timeout=timeout_s(task))
            r.raise_for_status()
            return r.json()["pipelineResponse"][0]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"bhashini {task}: {type(exc).__name__}") from exc

    async def stt(self, wav: bytes, lang: str | None) -> tuple[str, str]:
        # Bhashini ASR needs the spoken language; without a hint use the deployment default.
        lang = lang or env("STT_DEFAULT_LANG", "ta")
        out = await self._compute("asr", lang, None, {"audioFormat": "wav", "samplingRate": 16000},
                                  {"audio": [{"audioContent": base64.b64encode(wav).decode()}]})
        return out["output"][0]["source"], lang

    async def translate(self, text: str, src: str, tgt: str) -> str:
        out = await self._compute("translation", src, tgt, {}, {"input": [{"source": text}]})
        return out["output"][0]["target"]

    async def tts(self, text: str, lang: str, voice: str | None) -> tuple[bytes, str]:
        gender = voice if voice in ("male", "female") else env("BHASHINI_TTS_GENDER", "female")
        out = await self._compute("tts", lang, None, {"gender": gender}, {"input": [{"source": text}]})
        return base64.b64decode(out["audio"][0]["audioContent"]), "audio/wav"
