"""The connector to browser-product/, against a fake of its v1 API."""
import base64
import io
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.browser import BrowserError, BrowserSessionLost
from app.browser_product import BrowserProductWorker
from contracts.browser import Action, FileRules, Target
from tests.conftest import FakeLlm, Network
from tests.test_telegram import BOT_TOKEN, SECRET, TelegramChat

BASE = "http://browser.test"
KEY = "service-key"
OTP = "246810"
ANSWER = "7"
REVIEW_HASH = "a" * 64
PROFILE = {
    "full_name": "Demo Student",
    "course": "Class 12",
    "annual_income": "120000",
    "state": "Tamil Nadu",
    "community": "BC / MBC",
}


class FakeService:
    """Follows the state machine captured from the running service."""

    def __init__(self) -> None:
        self.state = "otp_needed"
        self.started: dict[str, Any] = {}
        self.commands: list[dict[str, Any]] = []
        self.receipt: str | None = None
        self.approvals = 0
        self.keys: set[str] = set()
        self.upload = {"mime": "application/pdf", "max_bytes": 1048576}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.keys.add(request.headers.get("X-Internal-Key", ""))
        if path == "/integration/v1/portals":
            return httpx.Response(200, json={"portals": [
                {"id": "another-portal", "application_flow": False},
                {"id": "mock-scholarship", "application_flow": True, "upload": self.upload},
            ]})
        if path == "/integration/v1/sessions":
            self.started = body
            return httpx.Response(201, json={"id": "s1", "state": self.state})
        if path == "/integration/v1/sessions/gone":
            return httpx.Response(404, json={})
        if path == "/integration/v1/sessions/s1":
            return httpx.Response(200, json={
                "id": "s1", "state": self.state, "review_hash": REVIEW_HASH,
                "receipt_id": self.receipt,
            })
        if path == "/integration/v1/sessions/s1/commands":
            return self._command(body)
        if path == "/integration/v1/human-tasks":
            return httpx.Response(201, json={
                "task_id": "t1", "assistance_path": "/assist/t1#invitation-value",
            })
        if path == "/assist-api/t1/claim":
            assert body == {"invitation": "invitation-value"}
            return httpx.Response(200, json={"bearer": "bearer-value"})
        if path == "/assist-api/t1/view":
            assert request.headers["Authorization"] == "Bearer bearer-value"
            image = base64.b64encode(b"challenge-crop").decode()
            return httpx.Response(200, json={"screenshot_base64": image})
        if path == "/assist-api/t1/answer":
            assert request.headers["Authorization"] == "Bearer bearer-value"
            right = body["answer"] == ANSWER
            if right:
                self.state = "form_ready"
            return httpx.Response(200, json={"ok": right, "session_state": self.state})
        raise AssertionError(f"Unexpected call to {path}")

    def _command(self, body: dict[str, Any]) -> httpx.Response:
        self.commands.append(body)
        assert body["expected_state"] == self.state
        kind = body["kind"]
        if kind == "otp" and body["payload"]["otp"] == OTP:
            self.state = "captcha_needed"
        elif kind == "fill":
            self.state = "approval_needed"
        elif kind == "approve":
            assert body["payload"] == {"confirmed": True, "review_hash": REVIEW_HASH}
            self.approvals += 1
            self.receipt = "MOCK-2026-TEST"
            self.state = "submitted"
        return httpx.Response(200, json={"state": self.state})


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
def worker(service: FakeService, make_settings) -> BrowserProductWorker:
    settings = make_settings(browser_product_url=f"{BASE}/", browser_product_key=KEY)
    return BrowserProductWorker(settings, httpx.AsyncClient(transport=httpx.MockTransport(service)))


async def answer(worker: BrowserProductWorker, target: Target, submit: Target, value: str) -> None:
    await worker.act("s1", Action(type="type", target=target, value=value))
    await worker.act("s1", Action(type="click", target=submit))


def jpeg(size: tuple[int, int] = (300, 200), noise: bool = False) -> bytes:
    image = Image.effect_noise(size, 90).convert("RGB") if noise else Image.new("RGB", size, "white")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def upload_action(data: bytes = b"%PDF-1.4 document", mime_type: str = "application/pdf") -> Action:
    return Action(
        type="upload",
        target=Target(role="file", name="Upload document"),
        file_base64=base64.b64encode(data).decode(),
        file_mime=mime_type,
        file_name="marksheet.pdf",
    )


async def test_full_walk_through_the_portal(
    worker: BrowserProductWorker, service: FakeService
) -> None:
    assert await worker.open("mock-scholarship", PROFILE) == "s1"

    otp = (await worker.login("s1", "ignored")).challenge
    assert otp.kind == "otp"
    await answer(worker, otp.input, otp.submit, OTP)

    captcha = (await worker.snapshot("s1")).challenge
    assert captcha.kind == "captcha"
    assert base64.b64decode(captcha.image_base64) == b"challenge-crop"
    await answer(worker, captcha.input, captcha.submit, ANSWER)

    form = await worker.snapshot("s1")
    assert [node.name for node in form.nodes] == ["Upload document"]
    assert form.nodes[0].file_rules == FileRules(
        formats=["application/pdf"], max_bytes=1048576
    )
    assert (await worker.act("s1", upload_action())).ok

    form = await worker.snapshot("s1")
    assert [node.name for node in form.nodes] == ["Fill application"]
    await worker.act("s1", Action(type="click", target=Target(role="button", name="Fill application")))
    sent = service.commands[-1]["payload"]
    assert set(sent) == {"subject", "source_ref", "file_name", "file_base64"}
    assert sent["subject"] == service.started["subject"]
    assert sent["file_name"] == "marksheet.pdf"
    assert base64.b64decode(sent["file_base64"]) == b"%PDF-1.4 document"

    review = await worker.snapshot("s1")
    assert [node.name for node in review.nodes] == ["Final submit"]
    assert review.managed_fields["annual_income"] == "Annual income"
    assert service.approvals == 0  # Reaching review submits nothing.

    await worker.act("s1", Action(type="click", target=Target(role="button", name="Final submit")))
    assert (await worker.snapshot("s1")).receipt_number == "MOCK-2026-TEST"
    assert service.approvals == 1
    assert service.keys == {KEY}


async def test_fields_are_mapped_to_the_service(
    worker: BrowserProductWorker, service: FakeService
) -> None:
    await worker.open("mock-scholarship", PROFILE)
    fields = service.started["fields"]
    assert fields["student_name"]["value"] == "Demo Student"
    assert fields["income"]["value"] == "120000"
    assert fields["category"]["value"] == "BC"
    assert fields["state"]["verified"] is True
    assert "91" not in service.started["subject"][:2]


async def test_missing_profile_field_is_a_clear_error(worker: BrowserProductWorker) -> None:
    with pytest.raises(BrowserError, match="full_name"):
        await worker.open("mock-scholarship", {**PROFILE, "full_name": ""})


async def test_wrong_otp_shows_the_challenge_again(worker: BrowserProductWorker) -> None:
    await worker.open("mock-scholarship", PROFILE)
    otp = (await worker.snapshot("s1")).challenge
    await answer(worker, otp.input, otp.submit, "000000")
    assert (await worker.snapshot("s1")).challenge.kind == "otp"


async def test_otp_is_not_kept_after_it_is_used(
    worker: BrowserProductWorker, service: FakeService
) -> None:
    await worker.open("mock-scholarship", PROFILE)
    otp = (await worker.snapshot("s1")).challenge
    await answer(worker, otp.input, otp.submit, OTP)
    assert worker._typed == {}


async def test_lost_session_is_reported(worker: BrowserProductWorker) -> None:
    with pytest.raises(BrowserSessionLost):
        await worker.snapshot("gone")


async def test_unreachable_service_is_a_browser_error(make_settings) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    settings = make_settings(browser_product_url=BASE, browser_product_key=KEY)
    worker = BrowserProductWorker(settings, httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    with pytest.raises(BrowserError):
        await worker.open("mock-scholarship", PROFILE)


async def at_form(worker: BrowserProductWorker, service: FakeService) -> None:
    await worker.open("mock-scholarship", PROFILE)
    service.state = "form_ready"


async def test_form_cannot_be_filled_without_a_document(
    worker: BrowserProductWorker, service: FakeService
) -> None:
    await at_form(worker, service)
    click = Action(type="click", target=Target(role="button", name="Fill application"))
    result = await worker.act("s1", click)
    assert result.ok is False
    assert service.commands == []


async def test_a_portal_stating_no_rule_leaves_the_file_alone(
    worker: BrowserProductWorker, service: FakeService
) -> None:
    service.upload = {}
    await at_form(worker, service)
    assert (await worker.snapshot("s1")).nodes[0].file_rules == FileRules()


async def test_cannot_submit_without_a_review(worker: BrowserProductWorker) -> None:
    result = await worker.act("s1", Action(type="click", target=Target(role="button", name="Final submit")))
    assert result.ok is False


async def test_unknown_button_fails(worker: BrowserProductWorker) -> None:
    result = await worker.act("s1", Action(type="click", target=Target(role="button", name="Delete")))
    assert result.ok is False


def full_chat(client: TestClient, network: Network) -> TelegramChat:
    network.telegram_file = jpeg()
    chat = TelegramChat(client)
    chat.text("/start")
    chat.press("consent:yes")
    chat.text("Tamil Nadu")
    chat.text("Class 12")
    chat.text("120000")
    chat.press("question_community:bc")
    chat.press("confirm:yes")
    chat.photo()
    chat.press("documents:done")
    chat.text("portal-user")
    chat.text(OTP)
    chat.text(ANSWER)
    return chat


def agent_client(make_settings, network: Network, service: FakeService, **overrides: Any):
    from app.main import create_app
    from app.plugins import Plugins
    from app.standins import StubExtractor

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "browser.test":
            return service(request)
        return network(request)

    settings = make_settings(
        browser_product_url=BASE,
        browser_product_key=KEY,
        telegram_bot_token=BOT_TOKEN,
        telegram_webhook_secret=SECRET,
        **overrides,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    return TestClient(create_app(settings, http, None, Plugins(extraction=StubExtractor())))


class PortalModel(FakeLlm):
    """Plays the model: presses the only control on each page."""

    def _next_step(self, user: str, nodes: list[dict[str, str]]) -> dict[str, Any]:
        for node in nodes:
            if node["name"] == "Upload document":
                return {
                    "action": "upload", "ref": node["ref"], "document": "marksheet",
                    "intent": "Attach the marksheet",
                }
            if node["name"] == "Fill application":
                return {"action": "click", "ref": node["ref"], "intent": "Fill the application"}
        return {"action": "review", "intent": "Form complete"}


@pytest.mark.parametrize(
    ("upload", "start", "name"),
    [
        ({"mime": "application/pdf", "max_bytes": 1048576}, b"%PDF-", "marksheet.pdf"),
        ({"mime": "image/jpeg", "max_bytes": 40000}, b"\xff\xd8", "marksheet.jpg"),
        ({"mime": "image/png", "max_bytes": 900000}, b"\x89PNG", "marksheet.png"),
    ],
)
def test_each_portal_decides_what_the_agent_sends(
    make_settings, network: Network, service: FakeService,
    upload: dict[str, Any], start: bytes, name: str,
) -> None:
    network.llm = PortalModel()
    service.upload = upload
    with agent_client(make_settings, network, service) as client:
        full_chat(client, network)
        sent = next(c["payload"] for c in service.commands if c["kind"] == "fill")
        data = base64.b64decode(sent["file_base64"])
        assert data.startswith(start)
        assert len(data) <= upload["max_bytes"]
        assert sent["file_name"] == name


def test_agent_stops_at_review_with_the_fields_listed(
    make_settings, network: Network, service: FakeService
) -> None:
    network.llm = PortalModel()
    with agent_client(make_settings, network, service) as client:
        chat = full_chat(client, network)

        review = network.telegram_texts()[-1]
        assert "1. Student name: Demo Student" in review
        assert "3. Annual income: 120000" in review
        assert service.state == "approval_needed"

        chat.press("approval:approve")
        assert "Nothing has been submitted" in network.telegram_texts()[-1]
        assert service.approvals == 0


def test_agent_submits_after_approval_when_allowed(
    make_settings, network: Network, service: FakeService
) -> None:
    network.llm = PortalModel()
    with agent_client(make_settings, network, service, allow_real_submit=True) as client:
        chat = full_chat(client, network)
        assert service.approvals == 0

        chat.press("approval:approve")
        assert service.approvals == 1
        assert any("MOCK-2026-TEST" in text for text in network.telegram_texts())


def test_portal_values_never_reach_the_model(
    make_settings, network: Network, service: FakeService
) -> None:
    network.llm = PortalModel()
    with agent_client(make_settings, network, service) as client:
        full_chat(client, network)

    prompts = "\n".join(network.llm.prompts)
    assert prompts
    for secret in ("Demo Student", "120000", OTP, "portal-user"):
        assert secret not in prompts
