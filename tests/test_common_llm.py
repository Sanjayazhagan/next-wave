"""common.llm against a fake OpenAI-compatible endpoint (test double)."""
import json

import httpx
import pytest
from pydantic import BaseModel

from common import llm


class Answer(BaseModel):
    doc_type: str


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
                          request=httpx.Request("POST", "http://x"))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("VISION_MODEL", "vision-model")
    monkeypatch.setenv("LLM_MODEL", "text-model")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    return tmp_path


def test_vision_json_retries_once_then_logs_without_content(env, monkeypatch):
    replies = iter(["```json\n{\"wrong\": 1}\n```", "Sure: {\"doc_type\": \"marksheet\"}"])
    sent = []

    def fake_post(url, headers, json, timeout):
        sent.append(json)
        return _reply(next(replies))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    before = llm.llm_calls_total()
    out = llm.vision_json([b"\xff\xd8fake"], "What is it?", Answer, caller="t")
    assert out.doc_type == "marksheet"
    assert llm.llm_calls_total() - before == 2
    assert sent[0]["model"] == "vision-model"
    assert sent[0]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    log = (env / "llm.jsonl").read_text()
    assert "marksheet" not in log and "What is it" not in log
    assert [json.loads(line)["ok"] for line in log.splitlines()] == [False, True]


def test_missing_model_env_raises(env, monkeypatch):
    monkeypatch.delenv("LLM_MODEL")
    with pytest.raises(llm.LLMError, match="LLM_MODEL"):
        llm.text_json("hi", Answer, caller="t")
