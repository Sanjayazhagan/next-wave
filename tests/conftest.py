import asyncio
import base64
import hashlib
import inspect
import hmac
import io
import json
import os
import time
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.plugins import Plugins
from app.standins import StubBrowser, StubExtractor

# Tests talk to fake LLMs, so the real per-minute pacing (common/pace.py) is off.
# tests/test_pace.py sets its own limits.
os.environ.setdefault("LLM_RPM", "0")
os.environ.setdefault("LLM_TPM", "0")

APP_SECRET = "test-secret"
VERIFY_TOKEN = "test-verify-token"
API_TOKEN = "test-api-token"
PHONE = "919876543210"
LANGUAGE_URL = "http://language.test"
LLM_URL = "http://llm.test/v1"
AADHAAR = "2345 6789 0123"

FIELD_FOR_LABEL = {
    "Full name": "full_name",
    "Date of birth": "date_of_birth",
    "Annual income": "annual_income",
}


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run `async def` tests, so no extra pytest plugin is needed."""
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    arguments = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(pyfuncitem.obj(**arguments))
    return True


def tone_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x10" * 8000)
    return buffer.getvalue()


class FakeLlm:
    """Plays the model: fills labelled fields, uploads, then continues."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.chat_prompts: list[str] = []
        # Replies for the AI chat. When empty it fails, so the fixed questions run.
        self.chat_replies: list[Any] = []
        self.press_final_submit = False

    def __call__(self, body: dict[str, Any]) -> str:
        system, user = (message["content"] for message in body["messages"])
        if "You are Dakiya" in system:
            self.chat_prompts.append(user)
            if not self.chat_replies:
                return "not json"
            reply = self.chat_replies.pop(0)
            return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        self.prompts.append(system + "\n" + user)
        nodes = [json.loads(line) for line in user.splitlines() if line.startswith("{")]
        if "saved step" in system:
            return self._repair(user, nodes)
        return json.dumps(self._next_step(user, nodes))

    @staticmethod
    def _repair(user: str, nodes: list[dict[str, str]]) -> str:
        wanted = "Proceed" if "Continue" in user else "Full name"
        for node in nodes:
            if wanted in node["name"]:
                return f"```json\n{json.dumps({'ref': node['ref'], 'reasoning': 'Same job'})}\n```"
        return json.dumps({"ref": None, "reasoning": "Not found"})

    def _next_step(self, user: str, nodes: list[dict[str, str]]) -> dict[str, Any]:
        for node in nodes:
            field = FIELD_FOR_LABEL.get(node["name"])
            if field and not node["value"]:
                return {
                    "action": "type",
                    "ref": node["ref"],
                    "field": field,
                    "intent": f"Fill {node['name']}",
                    "reasoning": f"{node['name']} is empty",
                }
        by_name = {node["name"]: node["ref"] for node in nodes}
        if "Upload marksheet" in by_name and "Upload marksheet" not in user.split("PAGE:")[0]:
            return {
                "action": "upload",
                "ref": by_name["Upload marksheet"],
                "document": "marksheet",
                "intent": "Upload marksheet",
            }
        if "Continue" in by_name:
            return {"action": "click", "ref": by_name["Continue"], "intent": "Continue"}
        if self.press_final_submit and "Final submit" in by_name:
            return {"action": "click", "ref": by_name["Final submit"], "intent": "Submit"}
        return {"action": "review", "intent": "Form complete"}


class Network:
    """Answers every outbound HTTP call the app makes."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.uploads: list[httpx.Request] = []
        self.llm = FakeLlm()
        self.llm_calls = 0
        self.translated: list[dict[str, str]] = []
        self.heard_language = "ta"
        self.telegram: list[tuple[str, dict[str, Any]]] = []
        self.telegram_error: str | None = None
        self.telegram_file = b"telegram-file-bytes"

    def _telegram(self, request: httpx.Request) -> httpx.Response:
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=self.telegram_file)
        method = request.url.path.rsplit("/", 1)[-1]
        is_json = request.headers.get("content-type", "").startswith("application/json")
        self.telegram.append((method, json.loads(request.content) if is_json else {}))
        if self.telegram_error:
            return httpx.Response(
                400, json={"ok": False, "description": self.telegram_error}
            )
        if method == "getFile":
            result: Any = {"file_path": "photos/a.jpg", "file_size": 10}
        else:
            result = True
        return httpx.Response(200, json={"ok": True, "result": result})

    def telegram_calls(self, method: str) -> list[dict[str, Any]]:
        return [body for name, body in self.telegram if name == method]

    def telegram_texts(self) -> list[str]:
        return [body["text"] for body in self.telegram_calls("sendMessage")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.telegram.org" in url:
            return self._telegram(request)
        if url.startswith(LLM_URL):
            before = len(self.llm.prompts)
            reply = self.llm(json.loads(request.content))
            self.llm_calls += len(self.llm.prompts) - before  # Portal planning only.
            return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
        if url.startswith(LANGUAGE_URL):
            return self._language(request)
        if url.endswith("/messages"):
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "sent"}]})
        if url.endswith("/media"):
            self.uploads.append(request)
            return httpx.Response(200, json={"id": f"media-{len(self.uploads)}"})
        if "lookaside" in url:
            return httpx.Response(200, content=b"file-bytes")
        if "graph.facebook.com" in url:
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/file",
                    "mime_type": "image/jpeg",
                    "file_size": 10,
                },
            )
        raise AssertionError(f"Unexpected call to {url}")

    def _language(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/stt":
            return httpx.Response(200, json={"text": "ஆம்", "language": self.heard_language})
        if request.url.path == "/translate":
            self.translated.append(body)
            return httpx.Response(200, json={"text": f"[{body['target']}] {body['text']}"})
        audio = base64.b64encode(tone_wav()).decode()
        return httpx.Response(200, json={"audio_base64": audio, "mime_type": "audio/wav"})

    def texts(self) -> list[str]:
        result = []
        for message in self.sent:
            if message["type"] == "text":
                result.append(message["text"]["body"])
            elif message["type"] == "interactive":
                result.append(message["interactive"]["body"]["text"])
        return result

    def last_text(self) -> str:
        return self.texts()[-1]

    def last_buttons(self) -> list[str]:
        message = next(m for m in reversed(self.sent) if m["type"] == "interactive")
        return [b["reply"]["id"] for b in message["interactive"]["action"]["buttons"]]


class Chat:
    """One phone talking to the webhook."""

    def __init__(self, client: TestClient, network: Network, phone: str = PHONE) -> None:
        self.client = client
        self.network = network
        self.phone = phone
        self.count = 0

    def post(self, payload: dict[str, Any], secret: str = APP_SECRET) -> httpx.Response:
        body = json.dumps(payload).encode()
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )

    def message(self, message_type: str, **content: Any) -> httpx.Response:
        self.count += 1
        message = {
            "from": self.phone,
            "id": f"wamid.{self.phone}.{self.count}.{time.time_ns()}",
            "type": message_type,
            **content,
        }
        return self.post(webhook(messages=[message]))

    def text(self, body: str) -> httpx.Response:
        return self.message("text", text={"body": body})

    def press(self, button_id: str) -> httpx.Response:
        reply = {"type": "button_reply", "button_reply": {"id": button_id, "title": "x"}}
        return self.message("interactive", interactive=reply)

    def photo(self) -> httpx.Response:
        return self.message("image", image={"id": "img1", "mime_type": "image/jpeg"})

    def voice(self) -> httpx.Response:
        audio = {"id": "aud1", "mime_type": "audio/ogg; codecs=opus", "voice": True}
        return self.message("audio", audio=audio)

    def up_to_documents(self) -> None:
        """Consent and the four questions."""
        self.text("hi")
        self.press("consent:yes")
        self.text("Tamil Nadu")
        self.text("Class 12")
        self.text("120000")
        self.press("question_community:bc")
        self.press("confirm:yes")

    def up_to_login(self) -> None:
        self.up_to_documents()
        self.photo()
        self.press("documents:done")

    def up_to_review(self) -> None:
        self.up_to_login()
        self.text("portal-user")
        self.text("123456")  # OTP
        self.text("ABCD")  # CAPTCHA


def webhook(**value: Any) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}],
    }


@pytest.fixture
def network() -> Network:
    return Network()


@pytest.fixture
def browser() -> StubBrowser:
    return StubBrowser()


@pytest.fixture
def plugins() -> Plugins:
    return Plugins(extraction=StubExtractor())


@pytest.fixture
def make_settings(tmp_path: Path):
    def build(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "whatsapp_phone_number_id": "12345",
            "whatsapp_app_secret": APP_SECRET,
            "whatsapp_access_token": "test-token",
            "whatsapp_verify_token": VERIFY_TOKEN,
            "vault_key": base64.b64encode(os.urandom(32)).decode(),
            "api_token": API_TOKEN,
            "database_path": tmp_path / "app.db",
            "checkpoint_path": tmp_path / "checkpoints.db",
            "files_path": tmp_path / "files",
            "llm_base_url": LLM_URL,
            "default_portal_id": "demo_portal",
            "choose_language": False,  # test_languages.py covers this step.
            **overrides,
        }
        return Settings(_env_file=None, **values)

    return build


@pytest.fixture
def make_client(network: Network, browser: StubBrowser, plugins: Plugins, make_settings):
    clients: list[TestClient] = []

    def build(settings: Settings | None = None, **overrides: Any) -> TestClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(network))
        app = create_app(
            settings or make_settings(**overrides), http, browser, plugins
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        try:
            client.__exit__(None, None, None)
        except RuntimeError:
            pass  # The kill test has already torn this client's event loop down.


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def chat(client: TestClient, network: Network) -> Chat:
    return Chat(client, network)


def session_id_for(client: TestClient) -> str:
    return client.app.state.sessions.active_for_phone(PHONE).id


def wait_for(condition, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out")
        time.sleep(0.02)


