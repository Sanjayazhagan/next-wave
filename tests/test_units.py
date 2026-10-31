import asyncio
import base64
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.exceptions import InvalidTag

from app.config import Settings
from app.llm import (
    DEFAULT_RATE_LIMIT_WAIT,
    MAX_RATE_LIMIT_WAIT,
    ChatLlm,
    LlmError,
    _rate_limit_wait,
    parse_json_object,
)
from app.planner import Planner, PlanError
from app.plugins import load_plugins
from app.redact import mask_for_display, redact
from app.skills import SkillStep, SkillStore
from app.vault import FileStore, Vault, decode_master_key
from contracts.browser import PageNode, Snapshot, Target
from contracts.vault import Receipt

KEY = os.urandom(32)
SUBMIT = Settings.model_fields["final_submit_pattern"].default


def test_vault_round_trip_and_encryption(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = Vault(path, KEY)
    vault.put_portal_id("919876543210", "tn", "USER-7")
    vault.put_receipt(
        "919876543210",
        Receipt(portal_id="tn", receipt_number="R1", submitted_at=datetime.now(UTC)),
    )
    assert vault.get_portal_id("919876543210", "tn") == "USER-7"
    assert vault.get_portal_id("919876543210", "other") is None
    assert [r.receipt_number for r in vault.list_receipts("919876543210")] == ["R1"]
    vault.close()

    raw = path.read_bytes() + (path.with_suffix(".db-wal").read_bytes() if path.with_suffix(".db-wal").exists() else b"")
    assert b"USER-7" not in raw
    assert b"919876543210" not in raw


def test_vault_rejects_the_wrong_key(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = Vault(path, KEY)
    vault.put_portal_id("owner", "tn", "USER-7")
    vault.close()

    other = Vault(path, os.urandom(32))
    assert other.get_portal_id("owner", "tn") is None  # A different key hashes owners differently.
    other.close()


def test_vault_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = Vault(path, KEY)
    vault.put_portal_id("owner", "tn", "USER-7")
    db = sqlite3.connect(path)
    db.execute("UPDATE vault SET name = 'other'")
    db.commit()
    db.close()
    with pytest.raises(InvalidTag):
        vault.get_portal_id("owner", "other")
    vault.close()


def test_file_store_round_trip(tmp_path: Path) -> None:
    files = FileStore(tmp_path / "f", KEY)
    ref = files.put(b"\x00document\x00bytes", "image/png")
    assert files.get(ref) == (b"\x00document\x00bytes", "image/png")
    assert b"document" not in (tmp_path / "f" / f"{ref}.bin").read_bytes()


def test_file_store_refuses_path_traversal(tmp_path: Path) -> None:
    files = FileStore(tmp_path / "f", KEY)
    with pytest.raises(ValueError):
        files.get("../../secrets")


def test_master_key_must_be_32_bytes() -> None:
    assert decode_master_key(base64.b64encode(KEY).decode()) == KEY
    with pytest.raises(ValueError):
        decode_master_key(base64.b64encode(b"short").decode())
    with pytest.raises(ValueError):
        decode_master_key("not base64!")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aadhaar 2345 6789 0123 ok", "Aadhaar <aadhaar> ok"),
        ("Aadhaar 234567890123", "Aadhaar <aadhaar>"),
        ("PAN ABCDE1234F", "PAN <pan>"),
        ("call +91 98765 43210".replace("98765 ", "98765"), "call <phone>"),
        ("mail a.b@example.com now", "mail <email> now"),
        ("IFSC SBIN0001234", "IFSC <ifsc>"),
        ("Account 12345678901", "Account <number>"),
        ("Income 120000 and year 2026", "Income 120000 and year 2026"),
    ],
)
def test_redact_patterns(text: str, expected: str) -> None:
    assert redact(text) == expected


def test_redact_known_values_use_whole_words() -> None:
    known = {"full_name": "Ravi", "community": "BC"}
    assert redact("Ravi Kumar, Ravichandran, BC", known) == "<field:full_name> Kumar, Ravichandran, BC"


def test_mask_for_display() -> None:
    assert mask_for_display("aadhaar_number", "2345 6789 0123") == "XXXX0123"
    assert mask_for_display("uid", "234567890123") == "XXXX0123"
    assert mask_for_display("bank_account", "12345") == "XXXX2345"
    assert mask_for_display("annual_income", "120000") == "120000"
    assert mask_for_display("date_of_birth", "01-06-2006") == "01-06-2006"


@pytest.mark.parametrize(
    "text",
    ['{"a": 1}', 'Sure!\n```json\n{"a": 1}\n```', 'Here you go: {"a": 1} done'],
)
def test_parse_json_object_tolerates_wrapping(text: str) -> None:
    assert parse_json_object(text) == {"a": 1}


@pytest.mark.parametrize("text", ["no json", "{broken", "[1, 2]"])
def test_parse_json_object_rejects_bad_replies(text: str) -> None:
    with pytest.raises(LlmError):
        parse_json_object(text)


def llm_settings(**overrides) -> Settings:
    values = {
        "whatsapp_phone_number_id": "1",
        "whatsapp_app_secret": "s",
        "whatsapp_access_token": "t",
        "whatsapp_verify_token": "v",
        "vault_key": "k",
        "api_token": "a",
        "llm_base_url": "http://llm.test/v1",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def fake_llm(replies: list[httpx.Response]) -> tuple[ChatLlm, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return replies.pop(0)

    return ChatLlm(llm_settings(), httpx.AsyncClient(transport=httpx.MockTransport(respond))), seen


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_llm_retries_after_a_rate_limit_and_a_bad_reply() -> None:
    llm, seen = fake_llm(
        [
            httpx.Response(429, headers={"retry-after": "0"}, json={}),
            chat_reply("not json"),
            chat_reply('{"ok": true}'),
        ]
    )
    assert asyncio.run(llm.complete_json("s", "u")) == {"ok": True}
    assert len(seen) == 3
    assert json.loads(seen[0].content)["model"] == "auto"


def test_rate_limit_waits_as_told_up_to_a_limit() -> None:
    def wait_for(headers: dict[str, str]) -> float:
        request = httpx.Request("POST", "http://llm.test")
        response = httpx.Response(429, headers=headers, request=request)
        return _rate_limit_wait(httpx.HTTPStatusError("429", request=request, response=response))

    assert wait_for({"retry-after": "7"}) == 7
    assert wait_for({"retry-after": "900"}) == MAX_RATE_LIMIT_WAIT
    assert wait_for({"retry-after": "soon"}) == DEFAULT_RATE_LIMIT_WAIT
    assert wait_for({}) == DEFAULT_RATE_LIMIT_WAIT
    assert _rate_limit_wait(LlmError("bad reply")) == 0


def test_llm_gives_up_after_three_attempts() -> None:
    llm, _ = fake_llm([httpx.Response(500, json={}) for _ in range(3)])
    with pytest.raises(LlmError):
        asyncio.run(llm.complete_json("s", "u"))


def test_llm_without_a_url_fails_clearly() -> None:
    llm = ChatLlm(llm_settings(llm_base_url=""), httpx.AsyncClient())
    with pytest.raises(LlmError, match="LLM_BASE_URL"):
        asyncio.run(llm.complete_json("s", "u"))


class ScriptedLlm:
    def __init__(self, reply: dict) -> None:
        self.reply = reply

    async def complete_json(self, system: str, user: str) -> dict:
        return self.reply


PAGE = Snapshot(
    url="https://portal.example/form?token=abc",
    title="Form",
    nodes=[
        PageNode(ref="a", role="textbox", name="Name"),
        PageNode(ref="b", role="button", name="Submit Application"),
        PageNode(ref="c", role="button", name="Save"),
    ],
)


def plan(reply: dict):
    planner = Planner(ScriptedLlm(reply), SUBMIT)
    return asyncio.run(planner.next_step("goal", PAGE, {"full_name": "Ravi"}, ["marksheet"], []))


def test_planner_turns_final_submit_click_into_review() -> None:
    assert plan({"action": "click", "ref": "b"}).action == "review"


def test_planner_accepts_a_normal_click() -> None:
    assert plan({"action": "click", "ref": "c"}).action == "click"


def test_planner_rejects_an_element_not_on_the_page() -> None:
    with pytest.raises(PlanError):
        plan({"action": "click", "ref": "zzz"})


def test_planner_rejects_an_unknown_action() -> None:
    with pytest.raises(PlanError):
        plan({"action": "delete_account", "ref": "a"})


def test_planner_asks_for_a_field_it_does_not_know() -> None:
    assert plan({"action": "type", "ref": "a", "field": "mother_name"}).action == "ask"


# Each of these was a real mistake made by a live free model.


def test_planner_refuses_to_type_into_a_button() -> None:
    with pytest.raises(PlanError):
        plan({"action": "type", "ref": "c", "field": "full_name"})


def test_asking_for_a_known_field_types_it_instead() -> None:
    step = plan({"action": "ask", "ref": "a", "field": "full_name"})
    assert (step.action, step.field) == ("type", "full_name")


def test_asking_for_a_known_field_without_an_input_is_refused() -> None:
    with pytest.raises(PlanError):
        plan({"action": "ask", "field": "full_name"})


def test_review_is_refused_before_the_final_submit_button_appears() -> None:
    form = PAGE.model_copy(update={"nodes": PAGE.nodes[:1] + PAGE.nodes[2:]})
    planner = Planner(ScriptedLlm({"action": "review"}), SUBMIT)
    with pytest.raises(PlanError):
        asyncio.run(planner.next_step("goal", form, {}, [], []))


@pytest.mark.parametrize("field", [None, "", "Your OTP please", "a" * 60])
def test_asking_needs_a_plain_field_name(field: str | None) -> None:
    with pytest.raises(PlanError):
        plan({"action": "ask", "field": field})


def test_planner_rejects_a_document_we_do_not_have() -> None:
    with pytest.raises(PlanError):
        plan({"action": "upload", "ref": "c", "document": "passport"})


def test_repair_cannot_point_at_final_submit() -> None:
    planner = Planner(ScriptedLlm({"ref": "b", "reasoning": "x"}), SUBMIT)
    step = SkillStep(intent="Continue", action="click", target=Target(role="button", name="Next"))
    with pytest.raises(PlanError):
        asyncio.run(planner.repair(step, PAGE, {}))


def test_page_url_query_string_is_not_sent_to_the_llm() -> None:
    captured = {}

    class Capturing(ScriptedLlm):
        async def complete_json(self, system: str, user: str) -> dict:
            captured["user"] = user
            return self.reply

    planner = Planner(Capturing({"action": "review"}), SUBMIT)
    asyncio.run(planner.next_step("goal", PAGE, {}, [], []))
    assert "token=abc" not in captured["user"]


def test_skill_versions_carry_counts_forward(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "s.db")
    steps = [SkillStep(intent="Fill name", action="type", target=Target(role="textbox", name="Name"), field="full_name")]
    assert store.save("tn", steps, repaired=False) == 1
    store.record_run("tn", 1)
    assert store.save("tn", steps, repaired=True) == 2

    latest = store.latest("tn")
    assert (latest.version, latest.runs, latest.repairs) == (2, 3, 1)
    assert latest.steps == steps
    assert store.latest("other") is None
    store.close()


def test_missing_modules_load_as_none() -> None:
    plugins = load_plugins()
    assert plugins.rules is None
    assert plugins.doctor is None
    assert plugins.extraction is None
    assert plugins.compressor is None
