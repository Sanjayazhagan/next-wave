"""Drop-downs and declaration boxes: the user decides, never the model."""
import pytest
from fastapi.testclient import TestClient

from app.browser_bridge import node_of
from app.graph.choices import match_option, pending_consent
from app.standins import StubBrowser
from contracts.browser import Action, ActionResult, NodeOption, PageNode, Snapshot
from tests.conftest import FIELD_FOR_LABEL, Chat, Network
from tests.test_agent_flow import session_status

BOX = "I confirm these details"
OPTIONS = [
    NodeOption(value="", label="Choose a course"),
    NodeOption(value="diploma", label="Diploma"),
    NodeOption(value="degree", label="Undergraduate degree"),
    NodeOption(value="pg", label="Postgraduate", disabled=True),
]


def test_an_answer_that_names_an_option_is_matched() -> None:
    assert match_option(OPTIONS, "degree").value == "degree"
    assert match_option(OPTIONS, "Undergraduate Degree").value == "degree"
    assert match_option(OPTIONS, " diploma ").value == "diploma"


def test_an_answer_that_names_nothing_is_never_guessed() -> None:
    assert match_option(OPTIONS, "B.E. first year") is None
    assert match_option(OPTIONS, "Postgraduate") is None  # Disabled.
    assert match_option(OPTIONS, "") is None


def snapshot_with(*nodes: PageNode) -> Snapshot:
    return Snapshot(url="https://portal.example/form", nodes=list(nodes))


def test_only_a_required_unticked_box_waits_for_the_user() -> None:
    required = PageNode(ref="a", role="checkbox", name=BOX, required=True)
    optional = PageNode(ref="b", role="checkbox", name="Send me news")
    ticked = PageNode(ref="c", role="checkbox", name="Done", required=True, checked=True)
    assert pending_consent(snapshot_with(optional, ticked)) is None
    assert pending_consent(snapshot_with(optional, ticked, required)).ref == "a"


def test_a_drop_down_and_a_required_box_keep_what_the_page_says() -> None:
    select = node_of({
        "ref": "e1", "role": "combobox", "name": "Course",
        "options": [{"value": "", "label": "Choose a course", "disabled": False},
                    {"value": "degree", "label": "Undergraduate degree"}],
    })
    assert [option.value for option in select.options] == ["", "degree"]
    box = node_of({"ref": "e2", "role": "checkbox", "name": BOX, "checked": False, "required": True})
    assert box.required and not box.checked


class FormBrowser(StubBrowser):
    """A form with a drop-down, and a review page with a required declaration box."""

    def __init__(self) -> None:
        super().__init__()
        self.ticked: set[str] = set()
        self.picked: dict[str, str] = {}
        self.box_actions: list[Action] = []
        self.course_on_review = False

    async def snapshot(self, session_id: str) -> Snapshot:
        snapshot = await super().snapshot(session_id)
        page = self._page(session_id)
        if page.step == "form":
            snapshot.nodes.insert(3, PageNode(
                ref="n9", role="combobox", name="Course", required=True,
                value=self.picked.get(session_id, ""), options=OPTIONS,
            ))
        if page.step == "review":
            if self.course_on_review:
                snapshot.nodes.insert(0, PageNode(
                    ref="r0", role="combobox", name="Course", required=True,
                    value=self.picked.get(session_id, ""), options=OPTIONS,
                ))
            box = PageNode(ref="r8", role="checkbox", name=BOX, required=True,
                           checked=session_id in self.ticked)
            snapshot.nodes.insert(len(snapshot.nodes) - 1, box)
        return snapshot

    async def act(self, session_id: str, action: Action) -> ActionResult:
        name = action.target.name if action.target else ""
        if name == "Course":
            if action.value not in ("diploma", "degree"):
                return ActionResult(ok=False, error="No such option")
            self.picked[session_id] = action.value
            return ActionResult(ok=True)
        if name == BOX:
            self.box_actions.append(action)
            if not (action.verified and action.source_ref):
                return ActionResult(ok=False, error="Verified input and source_ref are required")
            self.ticked.add(session_id)
            return ActionResult(ok=True)
        return await super().act(session_id, action)


@pytest.fixture
def browser() -> FormBrowser:
    return FormBrowser()


def test_a_declaration_box_waits_for_the_user_before_review(
    chat: Chat, client: TestClient, network: Network, browser: FormBrowser
) -> None:
    chat.up_to_review()

    assert session_status(client) == ("paused", "form_consent")
    assert BOX in network.last_text()
    assert network.last_buttons() == ["form_consent:yes", "form_consent:no"]
    assert browser.box_actions == []  # Nothing is ticked on the user's behalf yet.

    chat.press("form_consent:yes")

    assert [action.verified for action in browser.box_actions] == [True]
    assert browser.box_actions[0].source_ref.startswith("user:consent:")
    assert "Please check your application" in network.last_text()


def test_leaving_the_box_unticked_stops_without_submitting(
    chat: Chat, network: Network, browser: FormBrowser
) -> None:
    chat.up_to_review()
    chat.press("form_consent:no")

    assert "Nothing has been submitted" in network.last_text()
    assert browser.box_actions == []
    assert browser.final_submits == 0


def test_an_unclear_reply_about_the_box_asks_again(
    chat: Chat, client: TestClient, network: Network, browser: FormBrowser
) -> None:
    chat.up_to_review()
    chat.text("maybe")

    assert session_status(client) == ("paused", "form_consent")
    assert browser.box_actions == []


def test_a_drop_down_asks_the_user_to_pick(
    chat: Chat, client: TestClient, network: Network, browser: FormBrowser, monkeypatch
) -> None:
    monkeypatch.setitem(FIELD_FOR_LABEL, "Course", "course")
    chat.up_to_login()
    chat.text("portal-user")
    chat.text("123456")  # OTP

    assert session_status(client) == ("paused", "form_choice")
    assert "Course" in network.last_text()
    assert network.last_buttons() == ["form_choice:diploma", "form_choice:degree"]

    chat.text("masters")  # Not on the list, so it is asked again.
    assert session_status(client) == ("paused", "form_choice")
    assert browser.picked == {}

    chat.press("form_choice:degree")

    assert list(browser.picked.values()) == ["degree"]
    assert session_status(client)[1] == "captcha"


def test_a_click_on_a_drop_down_is_treated_as_a_choice(
    chat: Chat, client: TestClient, network: Network, browser: FormBrowser, monkeypatch
) -> None:
    original = type(network.llm)._next_step

    def clicking(self, user, nodes):
        course = next(node for node in nodes if node["name"] == "Course")
        if not course["value"]:
            return {"action": "click", "ref": course["ref"], "intent": "Open the Course dropdown"}
        return original(self, user, nodes)

    monkeypatch.setattr(type(network.llm), "_next_step", clicking)
    chat.up_to_login()
    chat.text("portal-user")
    chat.text("123456")  # OTP

    assert session_status(client) == ("paused", "form_choice")
    chat.press("form_choice:diploma")
    assert list(browser.picked.values()) == ["diploma"]


def test_a_required_drop_down_left_empty_is_asked_before_review(
    chat: Chat, client: TestClient, network: Network, browser: FormBrowser
) -> None:
    browser.course_on_review = True  # The model says the form is done, with a box still empty.
    chat.up_to_review()

    assert session_status(client) == ("paused", "form_choice")
    chat.press("form_choice:degree")

    assert list(browser.picked.values()) == ["degree"]
    assert session_status(client) == ("paused", "form_consent")  # Then the declaration box.
