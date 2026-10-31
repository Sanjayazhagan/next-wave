"""The real-page bridge, against a fake that keeps the service's real rules."""
import base64
import json
from typing import Any

import httpx
import pytest

from app.browser import BrowserError, BrowserSessionLost
from app.browser_bridge import BridgeBrowserWorker
from contracts.browser import Action, FileRules, Target

BASE = "http://browser.test"
KEY = "service-key"
PORTALS = json.dumps({"practice": "https://portal.example/form"})
FILE_NAME = "Income certificate (file upload; accepts: .pdf; required)"


class FakeBridge:
    def __init__(self) -> None:
        self.opened: dict[str, Any] = {}
        self.actions: list[dict[str, Any]] = []
        self.authorized: list[dict[str, Any]] = []
        self.refuse: int | None = None
        self.deleted = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Key"] == KEY
        path = request.url.path.removeprefix("/core-browser")
        body = json.loads(request.content) if request.content else {}
        if path == "/session":
            self.opened = body
            return httpx.Response(200, json={"session_id": "s1"})
        if path == "/session/gone/snapshot":
            return httpx.Response(404, json={})
        if path in ("/session/s1/snapshot", "/session/s1/login"):
            return httpx.Response(200, json={
                "url": "https://portal.example/form",
                "title": "Form",
                "nodes": [
                    {"ref": "e0", "role": "textbox", "name": "Full name", "value": ""},
                    {"ref": "e1", "role": "fileupload", "name": FILE_NAME, "value": "",
                     "accept": ".pdf", "description": "Maximum 200 KB", "upload_hint": ""},
                ],
                "page_text": "Maximum 200 KB",
                "screenshot_base64": None,
                "screenshot_masked": False,
                "challenge": None,
                "session_expired": False,
                "error": None,
                "receipt_number": None,
                "observation_id": "obs-1",
            })
        if path == "/session/s1/action":
            self.actions.append(body)
            if self.refuse:
                return httpx.Response(self.refuse, json={"detail": "refused"})
            return httpx.Response(200, json={"ok": True})
        if path == "/session/s1/authorize-submit":
            self.authorized.append(body)
            return httpx.Response(200, json={"authorized": True})
        if path == "/session/s1":
            self.deleted = True
            return httpx.Response(200, json={"closed": True})
        raise AssertionError(f"Unexpected call to {path}")


@pytest.fixture
def service() -> FakeBridge:
    return FakeBridge()


@pytest.fixture
def worker(service: FakeBridge, make_settings) -> BridgeBrowserWorker:
    settings = make_settings(
        browser_product_url=BASE, browser_product_key=KEY,
        browser_product_mode="bridge", portal_urls=PORTALS,
    )
    return BridgeBrowserWorker(settings, httpx.AsyncClient(transport=httpx.MockTransport(service)))


async def test_a_known_portal_opens_by_address(
    worker: BridgeBrowserWorker, service: FakeBridge
) -> None:
    assert await worker.open("practice") == "s1"
    assert service.opened == {"url": "https://portal.example/form", "consent_ref": "agent-consent"}


async def test_an_unlisted_portal_opens_by_id(
    worker: BridgeBrowserWorker, service: FakeBridge
) -> None:
    await worker.open("registered-on-the-service")
    assert service.opened == {"portal_id": "registered-on-the-service"}


async def test_upload_boxes_carry_this_forms_rules(worker: BridgeBrowserWorker) -> None:
    snapshot = await worker.snapshot("s1")
    name, upload = snapshot.nodes
    assert (name.role, name.file_rules) == ("textbox", None)
    assert upload.role == "file"
    assert upload.file_rules == FileRules(formats=["application/pdf"], max_bytes=200_000)


async def test_snapshot_keeps_page_text_limits_and_observation(
    worker: BridgeBrowserWorker,
) -> None:
    snapshot = await worker.snapshot("s1")
    assert snapshot.page_text == "Maximum 200 KB"
    assert snapshot.upload_limits.max_bytes == 1_048_576
    assert snapshot.observation_id == "obs-1"


async def test_login_returns_the_page(worker: BridgeBrowserWorker) -> None:
    assert (await worker.login("s1", "user")).title == "Form"


async def test_upload_uses_the_bridges_own_role_and_exact_name(
    worker: BridgeBrowserWorker, service: FakeBridge
) -> None:
    result = await worker.act("s1", Action(
        type="upload", target=Target(role="file", name=FILE_NAME),
        file_base64=base64.b64encode(b"%PDF-1.4").decode(),
        file_name="cert.pdf", file_mime="application/pdf",
    ))
    assert result.ok
    assert service.actions[0]["target"] == {"role": "fileupload", "name": FILE_NAME}


@pytest.mark.parametrize("status", [403, 409, 422])
async def test_a_refused_action_is_a_failed_step(
    status: int, worker: BridgeBrowserWorker, service: FakeBridge
) -> None:
    service.refuse = status
    click = Action(type="click", target=Target(role="button", name="Submit"))
    result = await worker.act("s1", click)
    assert result.ok is False
    assert str(status) in result.error


async def test_approval_is_tied_to_the_review_page(
    worker: BridgeBrowserWorker, service: FakeBridge
) -> None:
    await worker.authorize_submit("s1", "session-1", "obs-1")
    assert service.authorized == [{
        "approved": True, "approval_ref": "session-1", "review_observation_id": "obs-1",
    }]


async def test_lost_session_is_reported(worker: BridgeBrowserWorker) -> None:
    with pytest.raises(BrowserSessionLost):
        await worker.snapshot("gone")


async def test_unreachable_service_is_a_browser_error(make_settings) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    worker = BridgeBrowserWorker(
        make_settings(browser_product_url=BASE, browser_product_key=KEY),
        httpx.AsyncClient(transport=httpx.MockTransport(fail)),
    )
    with pytest.raises(BrowserError):
        await worker.open("practice")


async def test_close_ends_the_session(worker: BridgeBrowserWorker, service: FakeBridge) -> None:
    await worker.close("s1")
    assert service.deleted
