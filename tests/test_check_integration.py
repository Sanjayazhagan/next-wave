"""The checker must pass good modules and name exactly what is wrong with bad ones."""
import asyncio
import base64
from typing import Any

import httpx

from app.config import Settings
from app.plugins import Plugins
from contracts.doctor import DoctorResponse, Mismatch
from contracts.documents import ExtractedDocument, ExtractionResult
from contracts.eligibility import EligibilityResponse, SchemeMatch
from contracts.profile import Profile, ProfileField
from scripts.check_integration import (
    FAILED,
    MISSING,
    READY,
    check_browser,
    check_language,
    check_modules,
    guarded,
)


def field(value: str = "Asha") -> ProfileField:
    return ProfileField(value=value, source_document="marksheet", confidence=0.9)


def good_extract(images: list[Any]) -> ExtractionResult:
    fields = {"full_name": field()}
    document = ExtractedDocument(
        document_type="marksheet", fields=fields, file_ref=images[0].file_ref
    )
    return ExtractionResult(profile=Profile(fields=fields), documents=[document])


def good_rules(request: Any) -> EligibilityResponse:
    return EligibilityResponse(schemes=[
        SchemeMatch(scheme_id="pms", name="Post-Matric", portal_id="nsp", rank=1, cited_clause="3.1")
    ])


async def good_doctor(request: Any) -> DoctorResponse:
    return DoctorResponse(mismatches=[], risk_score=0.1)


def good_compressor(data: bytes, mime_type: str, portal_id: str, document_type: str) -> bytes:
    return data


def results_for(**modules: Any) -> dict[str, Any]:
    results = asyncio.run(check_modules(Plugins(**modules), None))
    return {result.name: result for result in results}


def test_nothing_merged_yet_says_what_to_add() -> None:
    result = results_for()["Eligibility rule engine"]
    assert (result.status, result.detail) == (MISSING, "add modules/rules.py")


def test_good_modules_are_ready() -> None:
    results = results_for(
        extraction=good_extract, rules=good_rules, doctor=good_doctor, compressor=good_compressor
    )
    assert [result.status for result in results.values()] == [READY] * 4


def test_module_returning_the_wrong_shape_is_named() -> None:
    result = results_for(rules=lambda request: {"schemes": [{"name": "x"}]})["Eligibility rule engine"]
    assert result.status == FAILED
    assert "does not match contracts/" in result.detail
    assert "scheme_id" in result.detail


def test_crashing_module_is_a_report_line_not_a_crash() -> None:
    def broken(request: Any) -> None:
        raise KeyError("oops")

    result = results_for(doctor=broken)["Application doctor"]
    assert result.status == FAILED
    assert "KeyError" in result.detail


def test_invented_field_name_is_caught() -> None:
    def extract(images: list[Any]) -> ExtractionResult:
        return ExtractionResult(profile=Profile(fields={"studentName": field()}), documents=[])

    result = results_for(extraction=extract)["Document extraction"]
    assert result.status == FAILED
    assert "studentName" in result.detail


def test_income_with_commas_is_caught() -> None:
    def extract(images: list[Any]) -> ExtractionResult:
        fields = {"annual_income": field("1,20,000")}
        return ExtractionResult(profile=Profile(fields=fields), documents=[])

    assert "digits only" in results_for(extraction=extract)["Document extraction"].detail


def test_changed_file_ref_is_caught() -> None:
    def extract(images: list[Any]) -> ExtractionResult:
        document = ExtractedDocument(document_type="x", fields={}, file_ref="other")
        return ExtractionResult(profile=Profile(), documents=[document])

    assert "file_ref" in results_for(extraction=extract)["Document extraction"].detail


def test_scheme_without_a_portal_is_caught() -> None:
    def rules(request: Any) -> EligibilityResponse:
        return EligibilityResponse(schemes=[
            SchemeMatch(scheme_id="a", name="A", portal_id="", rank=1, cited_clause="1")
        ])

    assert "portal_id" in results_for(rules=rules)["Eligibility rule engine"].detail


def test_doctor_repeating_an_aadhaar_number_is_caught() -> None:
    def doctor(request: Any) -> DoctorResponse:
        mismatch = Mismatch(field="aadhaar_number", detail="Differs from 234567890123")
        return DoctorResponse(mismatches=[mismatch], risk_score=0.5)

    assert results_for(doctor=doctor)["Application doctor"].status == FAILED


def test_compressor_returning_a_path_is_caught() -> None:
    result = results_for(compressor=lambda *args: "out.jpg")["File compressor"]
    assert "must return bytes" in result.detail


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None, whatsapp_phone_number_id="1", whatsapp_app_secret="s",
        whatsapp_access_token="t", whatsapp_verify_token="v", vault_key="k", api_token="a",
        **overrides,
    )


def run_check(check: Any, config: Settings, respond: Any) -> Any:
    async def go() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            return await guarded("check", lambda: check(config, http), False)

    return asyncio.run(go())


def test_language_service_contract_is_exercised() -> None:
    audio = base64.b64encode(b"audio").decode()

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "/translate": {"text": "வணக்கம்"},
            "/tts": {"audio_base64": audio, "mime_type": "audio/wav"},
            "/stt": {"text": "வணக்கம்", "language": "ta"},
        }[request.url.path])

    config = settings(language_service_url="http://language.test")
    assert run_check(check_language, config, respond).status == READY


def test_language_service_built_to_the_other_schema_is_caught() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"operation": "translate", "result_ref": "x"})

    config = settings(language_service_url="http://language.test")
    result = run_check(check_language, config, respond)
    assert result.status == FAILED
    assert "does not match contracts/" in result.detail


def test_wrong_browser_key_is_explained() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.url.path == "/ready" else 401, json={})

    config = settings(browser_product_url="http://browser.test", browser_product_key="bad")
    assert "refused" in run_check(check_browser, config, respond).detail


def test_unset_services_are_not_failures() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Nothing should be called")

    assert run_check(check_language, settings(), respond).status == MISSING
    assert run_check(check_browser, settings(), respond).status == MISSING


