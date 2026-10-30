import asyncio
import json

import httpx
import pytest

from app.browser import BrowserError, BrowserSessionLost, HttpBrowserWorker
from app.config import Settings
from contracts.browser import Action, Target

BASE = "http://browser.test"


def worker(respond) -> HttpBrowserWorker:
    settings = Settings(
        _env_file=None,
        whatsapp_phone_number_id="1",
        whatsapp_app_secret="s",
        whatsapp_access_token="t",
        whatsapp_verify_token="v",
        vault_key="k",
        api_token="a",
        browser_worker_url=f"{BASE}/",
    )
    return HttpBrowserWorker(settings, httpx.AsyncClient(transport=httpx.MockTransport(respond)))


def test_open_returns_the_session_id() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == f"{BASE}/session"
        assert json.loads(request.content) == {"portal_id": "tn"}
        return httpx.Response(200, json={"session_id": "s1"})

    assert asyncio.run(worker(respond).open("tn")) == "s1"


def test_login_and_snapshot_parse_the_contract() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "url": "https://portal.example/login",
                "nodes": [{"ref": "1", "role": "textbox", "name": "OTP"}],
                "challenge": {
                    "kind": "otp",
                    "input": {"role": "textbox", "name": "OTP"},
                },
            },
        )

    snapshot = asyncio.run(worker(respond).login("s1", "user"))
    assert snapshot.challenge.kind == "otp"
    assert snapshot.find(Target(role="textbox", name="OTP")).ref == "1"


def test_act_leaves_out_empty_fields() -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    action = Action(type="click", target=Target(role="button", name="Next"))
    assert asyncio.run(worker(respond).act("s1", action)).ok
    assert seen == {
        "path": "/session/s1/action",
        "body": {"type": "click", "target": {"role": "button", "name": "Next"}},
    }


def test_404_means_the_session_is_lost() -> None:
    with pytest.raises(BrowserSessionLost):
        asyncio.run(worker(lambda _: httpx.Response(404)).snapshot("gone"))


def test_server_error_is_a_browser_error() -> None:
    with pytest.raises(BrowserError):
        asyncio.run(worker(lambda _: httpx.Response(500)).snapshot("s1"))


def test_unreachable_worker_is_a_browser_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(BrowserError):
        asyncio.run(worker(respond).open("tn"))


def test_close_deletes_the_session() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("DELETE", "/session/s1")
        return httpx.Response(200)

    asyncio.run(worker(respond).close("s1"))
