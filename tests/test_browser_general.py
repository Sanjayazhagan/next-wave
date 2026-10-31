"""The v2 adapter, against a fake that enforces the service's real rules."""
import base64
import json
from typing import Any

import httpx
import pytest

from app.browser import BrowserError, BrowserSessionLost
from app.browser_general import GeneralBrowserWorker, name_of, role_of
from contracts.browser import Action, FileRules, Target

BASE = "http://browser.test"
KEY = "service-key"
PORTALS = json.dumps({"tn": "https://portal.example/start"})


def element(ref: str, **values: Any) -> dict[str, Any]:
    return {"ref": ref, "tag": "input", "type": "", "role": "", "label": "", "name": "", **values}


ELEMENTS = [
    element("e0", label="Full name"),
    element("e1", tag="select", label="District"),
    element("e2", type="file", label="Marksheet"),
    element("e3", tag="button", label="Next"),
    element("e4", tag="a", label="Help"),
    element("e5", tag="textarea", name="address"),
]


class FakeService:
    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.created: dict[str, Any] = {}
        self.artifacts: list[dict[str, Any]] = []
        self.waiting_human = False
        self.elements = ELEMENTS
        self.observations = 0
        self.refuse: int | None = None
        self.matched: bool | None = True
        self.deleted = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Key"] == KEY
        path = request.url.path.removeprefix("/integration/v2/browser")
        body = json.loads(request.content) if request.content else {}
        if path == "/contexts":
            self.created = body
            return httpx.Response(201, json={"id": "c1", "generation": 1, "state": "active"})
        if path == "/contexts/gone/observe":
            return httpx.Response(404, json={})
        if path == "/contexts/c1/observe":
            self.observations += 1
            return httpx.Response(200, json={
                "observation_id": f"obs-{self.observations}",
                "url": "https://portal.example/form",
                "title": "Form",
                "elements": self.elements,
                "waiting_human": self.waiting_human,
                "text": "Photo must be under 50 KB",
                "screenshot_base64": "aW1n",
            })
        if path == "/contexts/c1":
            if request.method == "DELETE":
                self.deleted = True
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"id": "c1", "state": "active"})
        if path == "/contexts/c1/artifacts":
            self.artifacts.append(body)
            return httpx.Response(201, json={"artifact_id": "a1"})
        if path == "/contexts/c1/actions":
            if self.refuse:
                return httpx.Response(self.refuse, json={"detail": "refused"})
            self.actions.append(body)
            assert body["observation_id"] == f"obs-{self.observations}"
            return httpx.Response(200, json={
                "status": "observed", "effect": {"check": "x", "matched": self.matched},
            })
        raise AssertionError(f"Unexpected call to {path}")


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
def worker(service: FakeService, make_settings) -> GeneralBrowserWorker:
    settings = make_settings(
        browser_product_url=BASE, browser_product_key=KEY,
        browser_product_mode="general", portal_urls=PORTALS,
    )
    return GeneralBrowserWorker(settings, httpx.AsyncClient(transport=httpx.MockTransport(service)))


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"tag": "input"}, "textbox"),
        ({"tag": "input", "type": "email"}, "textbox"),
        ({"tag": "input", "type": "checkbox"}, "checkbox"),
        ({"tag": "input", "type": "file"}, "file"),
        ({"tag": "input", "type": "submit"}, "button"),
        ({"tag": "select"}, "combobox"),
        ({"tag": "textarea"}, "textarea"),
        ({"tag": "a"}, "link"),
        ({"tag": "button"}, "button"),
        ({"tag": "div", "role": "button"}, "button"),
    ],
)
def test_roles_match_what_the_planner_expects(values: dict[str, str], expected: str) -> None:
    assert role_of(values) == expected


def test_names_fall_back_sensibly() -> None:
    assert name_of({"ref": "r", "label": "Name", "name": "n"}) == "Name"
    assert name_of({"ref": "r", "label": "", "name": "n"}) == "n"
    assert name_of({"ref": "r", "label": "", "name": ""}) == "r"


async def test_open_uses_the_portal_address_and_an_opaque_subject(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    assert await worker.open("tn", {"full_name": "Demo"}) == "c1"
    assert service.created["url"] == "https://portal.example/start"
    assert service.created["subject"].startswith("agent-")
    assert "Demo" not in json.dumps(service.created)


async def test_unknown_portal_says_what_to_set(worker: GeneralBrowserWorker) -> None:
    with pytest.raises(BrowserError, match="PORTAL_URLS"):
        await worker.open("nsp")


async def test_snapshot_gives_the_planner_nodes(worker: GeneralBrowserWorker) -> None:
    snapshot = await worker.snapshot("c1")
    assert snapshot.find(Target(role="textbox", name="Full name")).ref == "e0"
    assert snapshot.find(Target(role="button", name="Next")).ref == "e3"
    assert snapshot.screenshot_masked is True


async def test_page_of_only_login_controls_goes_to_a_helper(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.waiting_human = True
    service.elements = [element("p0", label="Password", risk="human_auth")]
    with pytest.raises(BrowserError, match="adapter"):
        await worker.snapshot("c1")


async def test_one_sensitive_box_is_hidden_and_the_form_carries_on(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.waiting_human = True
    service.elements = [*ELEMENTS, element("p0", label="Verification code", risk="human_auth")]
    snapshot = await worker.snapshot("c1")
    assert snapshot.find(Target(role="textbox", name="Full name")) is not None
    assert snapshot.find(Target(role="textbox", name="Verification code")) is None


async def test_typing_is_a_verified_fill_on_a_fresh_observation(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    await worker.snapshot("c1")
    action = Action(type="type", target=Target(role="textbox", name="Full name"), value="Demo")
    assert (await worker.act("c1", action)).ok

    sent = service.actions[-1]
    assert (sent["kind"], sent["target_ref"], sent["value"]) == ("fill", "e0", "Demo")
    assert sent["verified"] is True
    assert sent["observation_id"] == "obs-2"  # Not the one from the snapshot.


async def test_typing_into_a_select_uses_select(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    action = Action(type="type", target=Target(role="combobox", name="District"), value="Salem")
    await worker.act("c1", action)
    assert service.actions[-1]["kind"] == "select"


async def test_upload_sends_the_artifact_first(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    await worker.open("tn")
    action = Action(
        type="upload", target=Target(role="file", name="Marksheet"),
        file_base64=base64.b64encode(b"pdf").decode(), file_name="m.pdf",
        file_mime="application/pdf",
    )
    assert (await worker.act("c1", action)).ok
    assert service.artifacts[0]["subject"] == service.created["subject"]
    assert service.actions[-1]["artifact_id"] == "a1"


async def test_upload_after_a_restart_reopens_the_session(worker: GeneralBrowserWorker) -> None:
    action = Action(
        type="upload", target=Target(role="file", name="Marksheet"),
        file_base64=base64.b64encode(b"pdf").decode(), file_name="m.pdf",
        file_mime="application/pdf",
    )
    with pytest.raises(BrowserSessionLost):
        await worker.act("c1", action)


async def test_each_upload_control_states_its_own_rules(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.elements = [
        {"ref": "a", "tag": "input", "type": "file", "label": "Photo",
         "accept": "image/png,image/jpeg", "description": "Under 50 KB", "risk": "ordinary"},
        {"ref": "b", "tag": "input", "type": "file", "label": "Certificate (PDF, 2 MB)",
         "accept": "", "description": "", "risk": "ordinary"},
        {"ref": "c", "tag": "input", "type": "text", "label": "Name", "risk": "ordinary"},
    ]
    photo, certificate, name = (await worker.snapshot("c1")).nodes
    assert photo.file_rules == FileRules(
        formats=["image/png", "image/jpeg"], max_bytes=50_000
    )
    assert certificate.file_rules == FileRules(formats=["application/pdf"], max_bytes=2_000_000)
    assert name.file_rules is None


async def test_snapshot_passes_on_the_page_text_and_service_limits(
    worker: GeneralBrowserWorker,
) -> None:
    snapshot = await worker.snapshot("c1")
    assert snapshot.page_text == "Photo must be under 50 KB"
    assert snapshot.upload_limits.max_bytes == 1_048_576


async def test_upload_uses_the_spelling_the_form_lists(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.elements = [{
        "ref": "a", "tag": "input", "type": "file", "label": "Marksheet",
        "accept": ".jpeg", "risk": "ordinary",
    }]
    await worker.open("tn")
    action = Action(
        type="upload", target=Target(role="file", name="Marksheet"),
        file_base64=base64.b64encode(b"jpeg").decode(), file_name="m.jpg",
        file_mime="image/jpeg",
    )
    assert (await worker.act("c1", action)).ok
    assert service.artifacts[0]["file_name"] == "m.jpeg"


async def test_missing_element_fails_so_self_repair_can_run(worker: GeneralBrowserWorker) -> None:
    result = await worker.act("c1", Action(type="click", target=Target(role="button", name="Old")))
    assert result.ok is False


@pytest.mark.parametrize("status", [403, 409, 422])
async def test_refused_actions_are_failures_not_crashes(
    status: int, worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.refuse = status
    result = await worker.act("c1", Action(type="click", target=Target(role="button", name="Next")))
    assert result.ok is False


async def test_value_the_page_did_not_keep_is_a_failure(
    worker: GeneralBrowserWorker, service: FakeService
) -> None:
    service.matched = False
    action = Action(type="type", target=Target(role="textbox", name="Full name"), value="Demo")
    assert (await worker.act("c1", action)).ok is False


async def test_lost_context_is_reported(worker: GeneralBrowserWorker) -> None:
    with pytest.raises(BrowserSessionLost):
        await worker.snapshot("gone")


async def test_close_ends_the_context(worker: GeneralBrowserWorker, service: FakeService) -> None:
    await worker.close("c1")
    assert service.deleted is True
