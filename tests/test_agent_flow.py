"""Whole conversations, sent through the real webhook."""
import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.plugins import Plugins
from app.standins import RECEIPT, StubBrowser, StubExtractor
from contracts.doctor import DoctorRequest, DoctorResponse, Mismatch
from contracts.eligibility import EligibilityRequest, EligibilityResponse, SchemeMatch
from contracts.profile import ProfileField
from contracts.vault import Receipt
from tests.conftest import AADHAAR, LANGUAGE_URL, PHONE, Chat, Network, session_id_for, wait_for


def session_status(client: TestClient) -> tuple[str, str | None]:
    sid = session_id_for(client)
    session = client.app.state.sessions.get(sid)
    return session.status, session.pending_kind


def test_full_run_stops_at_review_without_submitting(
    chat: Chat, client: TestClient, network: Network, browser: StubBrowser
) -> None:
    chat.up_to_review()

    assert "Please check your application" in network.texts()[-1]
    assert session_status(client) == ("paused", "approval")

    chat.press("approval:approve")

    assert "Nothing has been submitted" in network.last_text()
    assert browser.final_submits == 0


def test_explored_run_is_saved_then_replayed_without_llm(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.up_to_review()
    chat.press("approval:approve")
    calls_after_explore = network.llm_calls
    assert calls_after_explore > 0

    chat.up_to_login()
    chat.text("123456")  # The portal ID is already in the vault, so OTP comes first.
    chat.text("ABCD")

    assert "Please check your application" in network.last_text()
    assert network.llm_calls == calls_after_explore


def test_broken_step_is_self_repaired_and_saved(
    chat: Chat, client: TestClient, network: Network, browser: StubBrowser
) -> None:
    chat.up_to_review()
    chat.press("approval:approve")

    browser.renames["Continue"] = "Proceed"  # What the chaos script does.

    chat.up_to_login()
    chat.text("123456")
    chat.text("ABCD")

    assert "Please check your application" in network.last_text()
    audit = client.get(
        f"/session/{session_id_for(client)}/audit", headers={"X-API-Key": "test-api-token"}
    ).json()
    repair = next(event for event in audit if event["step"] == "self_repair")
    assert "'Continue' is now 'Proceed'" in repair["message"]
    assert repair["reasoning"] == "Same job"

    # The repaired skill is saved, so the next run needs no LLM.
    calls = network.llm_calls
    chat.press("approval:approve")
    chat.up_to_login()
    chat.text("123456")
    chat.text("ABCD")
    assert "Please check your application" in network.last_text()
    assert network.llm_calls == calls


def test_edit_loop_refills_with_the_new_value(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.up_to_review()

    chat.press("approval:edit")
    assert "Reply with the number" in network.last_text()
    chat.text("nonsense")
    assert "couldn't read" in network.last_text()

    review = next(t for t in reversed(network.texts()) if "Please check" in t)
    number = next(line.split(".")[0] for line in review.splitlines() if "income" in line.lower())
    chat.text(f"{number} 150000")
    chat.text("123456")
    chat.text("ABCD")

    assert "Annual income: 150000" in network.last_text()
    profile = client.get(
        f"/session/{session_id_for(client)}", headers={"X-API-Key": "test-api-token"}
    ).json()["profile"]
    assert profile["annual_income"]["source_document"] == "user_edit"


def test_three_wrong_otps_hand_over_to_a_helper(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.up_to_login()
    chat.text("portal-user")
    chat.text("000001")
    chat.text("000002")
    chat.text("000003")

    assert "helper will take over" in network.last_text()
    assert session_status(client)[1] == "handover"

    # The user cannot talk their way past a handover.
    chat.text("123456")
    assert "helper is working" in network.last_text()
    assert session_status(client)[1] == "handover"

    # Only the session API can end or resume a handover.
    sid = session_id_for(client)
    response = client.post(
        f"/session/{sid}/handover", json={"action": "abort"}, headers={"X-API-Key": "test-api-token"}
    )
    assert response.status_code == 202
    assert "helper stopped" in network.last_text()


def test_handover_resume_retries_the_step(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.up_to_login()
    chat.text("portal-user")
    for wrong in ("1", "2", "3"):
        chat.text(wrong)
    sid = session_id_for(client)

    client.post(
        f"/session/{sid}/handover", json={"action": "resume"}, headers={"X-API-Key": "test-api-token"}
    )

    assert "OTP" in network.last_text()
    assert session_status(client) == ("paused", "otp")


def test_old_button_cannot_answer_a_new_prompt(chat: Chat, network: Network) -> None:
    chat.up_to_review()
    chat.press("consent:yes")
    assert "earlier message" in network.last_text()


def test_final_submit_only_happens_after_approval(
    make_client, network: Network, browser: StubBrowser
) -> None:
    client = make_client(allow_real_submit=True, language_service_url=LANGUAGE_URL)
    chat = Chat(client, network)
    network.llm.press_final_submit = True  # A confused or injected model.

    chat.up_to_review()
    assert browser.final_submits == 0

    chat.press("approval:approve")
    assert browser.final_submits == 1
    assert any(RECEIPT in text for text in network.texts())


def test_receipt_is_sent_as_text_and_tamil_voice_note(
    make_client, network: Network, browser: StubBrowser
) -> None:
    client = make_client(
        allow_real_submit=True, language_service_url=LANGUAGE_URL, default_language="as"
    )
    chat = Chat(client, network)
    chat.up_to_review()
    chat.press("approval:approve")

    voice = next(message for message in network.sent if message["type"] == "audio")
    assert voice["audio"]["voice"] is True
    upload = network.uploads[-1]
    assert b"OggS" in upload.content  # Real ffmpeg output.
    assert b"OpusHead" in upload.content
    assert any(RECEIPT in text and text.startswith("[as]") for text in network.texts())


def test_stopped_run_labels_an_earlier_receipt(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.up_to_review()
    client.app.state.vault.put_receipt(
        PHONE,
        Receipt(portal_id="demo_portal", receipt_number="REAL-77", submitted_at=datetime.now(UTC)),
    )
    chat.press("approval:approve")
    assert "Earlier genuine receipt, from a past application: REAL-77" in network.last_text()


def test_submit_is_never_repeated_after_a_crash(
    make_client, network: Network, browser: StubBrowser
) -> None:
    client = make_client(allow_real_submit=True)
    chat = Chat(client, network)
    chat.up_to_review()
    sid = session_id_for(client)

    assert client.app.state.sessions.claim_submit(sid)  # The first attempt got this far.
    chat.press("approval:approve")

    assert browser.final_submits == 0
    assert session_status(client)[1] == "handover"


def test_session_killed_mid_run_resumes_from_its_last_step(
    make_settings, make_client, network: Network, browser: StubBrowser
) -> None:
    class Killed(BaseException):
        pass

    settings = make_settings()
    first = make_client(settings)
    chat = Chat(first, network)
    chat.up_to_login()
    chat.text("portal-user")

    # The process dies while typing into the second field.
    real_act = browser.act
    typed = []

    async def dying_act(session_id, action):
        if action.type == "type" and action.value != "123456":
            typed.append(action.value)
            if len(typed) == 2:
                browser.act = real_act
                raise Killed
        return await real_act(session_id, action)

    browser.act = dying_act
    with pytest.raises(BaseException):
        chat.text("123456")

    sid = first.app.state.sessions.with_status("running")[0].id
    second = make_client(settings)
    wait_for(lambda: second.app.state.sessions.get(sid).status == "paused")

    assert second.app.state.sessions.get(sid).pending_kind == "captcha"
    assert typed[0] == "Demo Student"  # The first field was not lost.
    Chat(second, network).text("ABCD")
    assert second.app.state.sessions.get(sid).pending_kind == "approval"


def test_doctor_and_rules_are_used_when_merged(
    make_settings, network: Network, browser: StubBrowser, make_client, request
) -> None:
    def rank_schemes(request: EligibilityRequest) -> EligibilityResponse:
        assert "community" in request.profile.fields
        return EligibilityResponse(
            schemes=[
                SchemeMatch(
                    scheme_id="pms", name="Post-Matric Scholarship", portal_id="scholarship",
                    rank=1, cited_clause="Clause 3.1: income under 2.5 lakh",
                )
            ]
        )

    async def check_application(request: DoctorRequest) -> DoctorResponse:
        assert request.scheme_id == "pms"
        return DoctorResponse(
            mismatches=[Mismatch(field="full_name", detail="Differs on the income certificate")],
            risk_score=0.4,
        )

    plugins = request.getfixturevalue("plugins")
    plugins.rules = rank_schemes
    plugins.doctor = check_application
    chat = Chat(make_client(), network)

    chat.up_to_documents()
    assert "Clause 3.1" in network.last_text()
    chat.press("scheme:pms")
    assert "Please send photos" in network.last_text()
    chat.photo()
    chat.press("documents:done")
    chat.text("portal-user")
    chat.text("123456")
    chat.text("ABCD")

    assert "Differs on the income certificate" in network.last_text()


def test_no_matching_scheme_ends_politely(
    network: Network, make_client, request
) -> None:
    plugins = request.getfixturevalue("plugins")
    plugins.rules = lambda _: EligibilityResponse(schemes=[])
    chat = Chat(make_client(), network)
    chat.up_to_documents()
    assert "could not find a scheme" in network.last_text()


def test_missing_modules_are_skipped_cleanly(
    make_client, network: Network, request
) -> None:
    plugins: Plugins = request.getfixturevalue("plugins")
    plugins.extraction = None
    chat = Chat(make_client(), network)

    chat.up_to_login()
    assert "login ID" in network.last_text()


def test_declining_consent_ends_the_session(
    chat: Chat, client: TestClient, network: Network
) -> None:
    chat.text("hi")
    chat.press("consent:no")
    assert "Nothing was saved" in network.last_text()
    assert client.app.state.sessions.active_for_phone(PHONE) is None


def test_stop_cancels_the_session(chat: Chat, client: TestClient, network: Network) -> None:
    chat.text("hi")
    chat.press("consent:yes")
    chat.text("STOP")
    assert client.app.state.sessions.active_for_phone(PHONE) is None


def test_unclear_consent_asks_again(chat: Chat, network: Network) -> None:
    chat.text("hi")
    chat.text("what is this")
    assert network.last_buttons() == ["consent:yes", "consent:no"]


def test_field_missing_from_profile_is_asked_for(
    chat: Chat, client: TestClient, network: Network, browser: StubBrowser, plugins: Plugins
) -> None:
    extractor = StubExtractor()

    async def extract_without_dob(images):
        result = await extractor(images)
        del result.profile.fields["date_of_birth"]
        return result

    plugins.extraction = extract_without_dob
    chat.up_to_login()
    chat.text("portal-user")
    chat.text("123456")

    assert "date of birth" in network.last_text()
    chat.text("05-05-2005")
    chat.text("ABCD")
    assert "Please check your application" in network.last_text()


def test_voice_note_answers_a_prompt(make_client, network: Network) -> None:
    chat = Chat(make_client(language_service_url=LANGUAGE_URL, default_language="as"), network)
    chat.text("hi")
    network.translated.clear()
    chat.voice()
    # The model reply "ஆம்" is translated to "[en] ஆம்", which is not a yes word,
    # so the consent is asked again in the session language.
    assert any(call["target"] == "en" for call in network.translated)


def test_voice_note_without_language_service_asks_to_type(chat: Chat, network: Network) -> None:
    chat.text("hi")
    chat.voice()
    assert "Please type" in network.last_text()


def test_other_languages_use_the_language_service(make_client, network: Network) -> None:
    chat = Chat(make_client(language_service_url=LANGUAGE_URL, default_language="as"), network)
    chat.text("hi")
    assert network.last_text().startswith("[as] ")


def test_file_when_not_expected_is_refused(chat: Chat, network: Network) -> None:
    chat.text("hi")
    chat.photo()
    assert "not expecting a file" in network.last_text()


def test_captcha_image_is_sent_to_the_user(chat: Chat, network: Network) -> None:
    chat.up_to_login()
    chat.text("portal-user")
    chat.text("123456")
    assert any(message["type"] == "image" for message in network.sent)
    assert "security image" in network.last_text()


def test_unmasked_review_screenshot_is_not_sent(
    chat: Chat, network: Network, browser: StubBrowser
) -> None:
    real_snapshot = browser.snapshot

    async def with_screenshot(session_id):
        snapshot = await real_snapshot(session_id)
        snapshot.screenshot_base64 = base64.b64encode(b"page").decode()
        snapshot.screenshot_masked = False
        return snapshot

    browser.snapshot = with_screenshot
    chat.up_to_review()
    images = [m for m in network.sent if m["type"] == "image"]
    assert len(images) == 1  # Only the CAPTCHA crop.


# --- Privacy ---


def add_aadhaar(plugins: Plugins) -> None:
    extractor = StubExtractor()

    async def extract_with_aadhaar(images):
        result = await extractor(images)
        result.profile.fields["aadhaar_number"] = ProfileField(
            value=AADHAAR, source_document="aadhaar", confidence=0.99
        )
        return result

    plugins.extraction = extract_with_aadhaar


def test_llm_never_receives_personal_values(
    chat: Chat, network: Network, plugins: Plugins, browser: StubBrowser
) -> None:
    add_aadhaar(plugins)
    chat.up_to_review()

    prompts = "\n".join(network.llm.prompts)
    assert prompts
    for secret in ("Demo Student", "01-06-2006", "120000", "123456", "ABCD", PHONE):
        assert secret not in prompts
    assert AADHAAR not in prompts
    assert AADHAAR.replace(" ", "") not in prompts
    assert "<field:full_name>" in prompts  # Filled fields show as placeholders.


def test_nothing_personal_is_stored_in_plain_text(
    chat: Chat, tmp_path: Path, plugins: Plugins
) -> None:
    add_aadhaar(plugins)
    chat.up_to_review()

    stored = b"".join(
        path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    )
    for secret in (AADHAAR, "Demo Student", "portal-user", "123456"):
        assert secret.encode() not in stored
    assert b"file-bytes" not in stored  # The uploaded document.


def test_aadhaar_is_masked_on_the_review_message(
    chat: Chat, network: Network, plugins: Plugins, browser: StubBrowser
) -> None:
    add_aadhaar(plugins)
    chat.up_to_review()
    assert AADHAAR not in "\n".join(network.texts())


# --- Order of the conversation ---


def test_questions_come_before_documents(chat: Chat, network: Network) -> None:
    chat.text("hi")
    chat.press("consent:yes")
    assert "Which state" in network.last_text()
    chat.text("Tamil Nadu")
    chat.text("Class 12")
    chat.text("120000")
    chat.press("question_community:bc")
    assert "Is everything correct?" in network.last_text()
    chat.press("confirm:yes")
    assert "Please send photos" in network.last_text()


def test_done_with_no_document_says_so(chat: Chat, network: Network) -> None:
    chat.up_to_documents()
    chat.press("documents:done")
    assert "at least one document" in network.last_text()

    chat.photo()
    assert "Got it" in network.last_text()
    chat.press("documents:done")
    assert "login ID" in network.last_text()


def test_answers_survive_reading_the_documents(
    client: TestClient, chat: Chat, plugins: Plugins
) -> None:
    extractor = StubExtractor()

    async def extract_with_income(images):
        result = await extractor(images)
        result.profile.fields["annual_income"] = ProfileField(
            value="999999", source_document="income", confidence=0.99
        )
        return result

    plugins.extraction = extract_with_income
    chat.up_to_login()

    profile = client.get(
        f"/session/{session_id_for(client)}", headers={"X-API-Key": "test-api-token"}
    ).json()["profile"]
    assert profile["annual_income"] == {
        "value": "120000", "source_document": "user_answer", "confidence": 1.0
    }
    assert profile["full_name"]["source_document"] == "marksheet"
