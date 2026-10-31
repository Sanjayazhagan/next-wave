"""Checks every plug-in point against contracts/ and says what is ready.

    uv run python -m scripts.check_integration
    uv run python -m scripts.check_integration --document path/to/marksheet.jpg

A module that passes here works in the agent, with no change to the agent.
"""
import argparse
import asyncio
import shutil
import base64
import inspect
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.plugins import Plugins, load_plugins
from contracts.doctor import DoctorRequest, DoctorResponse
from contracts.documents import DocumentImage, ExtractionResult
from contracts.eligibility import EligibilityRequest, EligibilityResponse
from contracts.language import SttResponse, TranslateResponse, TtsResponse
from contracts.profile import FIELD_NAMES, Profile, ProfileField

READY = "READY"
MISSING = "not yet"
FAILED = "FAILED"
SENSITIVE_WORDS = ("aadhaar", "bank", "account")
# A 1x1 PNG, used when no real document is given.
SAMPLE_IMAGE = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)
SAMPLE_PROFILE = Profile(
    fields={
        name: ProfileField(value=value, source_document="user_answer", confidence=1.0)
        for name, value in {
            "full_name": "Demo Student",
            "state": "Tamil Nadu",
            "course": "Class 12",
            "annual_income": "120000",
            "community": "BC / MBC",
        }.items()
    }
)


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


async def run_module(function: Callable, *args: Any) -> Any:
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


def problems_with_fields(fields: dict[str, ProfileField]) -> list[str]:
    problems = []
    unknown = sorted(set(fields) - set(FIELD_NAMES))
    if unknown:
        problems.append(f"unknown field names {unknown}: see FIELD_NAMES in contracts/profile.py")
    for name, field in fields.items():
        if name == "annual_income" and not field.value.isdigit():
            problems.append("annual_income must be digits only, such as 120000")
        if not field.source_document:
            problems.append(f"{name} has no source_document")
    return problems


async def check_extraction(function: Callable, document: Path | None) -> Result:
    # Without Tesseract his pipeline skips every document, and only logs a warning.
    if function.__module__.startswith("modules.extraction") and not shutil.which("tesseract"):
        return Result("Document extraction", FAILED, "install tesseract-ocr, or nothing is read")
    data = document.read_bytes() if document else SAMPLE_IMAGE
    mime_type = "application/pdf" if document and document.suffix == ".pdf" else "image/jpeg"
    image = DocumentImage(file_ref="a" * 32, mime_type=mime_type, data=data)
    result = ExtractionResult.model_validate(await run_module(function, [image]))
    problems = problems_with_fields(result.profile.fields)
    for extracted in result.documents:
        if extracted.file_ref != image.file_ref:
            problems.append("documents must keep the file_ref they were given")
    if problems:
        return Result("Document extraction", FAILED, "; ".join(problems))
    note = f"{len(result.profile.fields)} fields read"
    return Result("Document extraction", READY, note if document else f"{note}, on a blank image")


async def check_rules(function: Callable) -> Result:
    request = EligibilityRequest(profile=SAMPLE_PROFILE)
    result = EligibilityResponse.model_validate(await run_module(function, request))
    problems = []
    for scheme in result.schemes:
        if not scheme.portal_id:
            problems.append(f"{scheme.scheme_id} has no portal_id")
        if not scheme.cited_clause:
            problems.append(f"{scheme.scheme_id} has no cited_clause")
    if len({scheme.rank for scheme in result.schemes}) != len(result.schemes):
        problems.append("each scheme needs its own rank")
    if problems:
        return Result("Eligibility rule engine", FAILED, "; ".join(problems))
    return Result("Eligibility rule engine", READY, f"{len(result.schemes)} schemes for a sample profile")


async def check_doctor(function: Callable) -> Result:
    request = DoctorRequest(profile=SAMPLE_PROFILE, documents=[], scheme_id="sample")
    result = DoctorResponse.model_validate(await run_module(function, request))
    for mismatch in result.mismatches:
        if any(char.isdigit() for char in mismatch.detail) and any(
            word in mismatch.field.lower() for word in SENSITIVE_WORDS
        ):
            return Result("Application doctor", FAILED, "details must not repeat ID numbers")
    return Result("Application doctor", READY, f"risk score {result.risk_score}")


async def check_compressor(function: Callable) -> Result:
    result = await run_module(function, SAMPLE_IMAGE, "image/png", "sample_portal", "marksheet")
    if not isinstance(result, bytes):
        return Result("File compressor", FAILED, f"must return bytes, not {type(result).__name__}")
    return Result("File compressor", READY, f"returned {len(result)} bytes")


async def check_language(settings: Settings, http: httpx.AsyncClient) -> Result:
    name = "Language service"
    base = settings.language_service_url.rstrip("/")
    if not base:
        return Result(name, MISSING, "set LANGUAGE_SERVICE_URL")
    translated = await http.post(
        f"{base}/translate", json={"text": "Hello", "source": "en", "target": "ta"}, timeout=30
    )
    TranslateResponse.model_validate(translated.raise_for_status().json())
    spoken = await http.post(f"{base}/tts", json={"text": "வணக்கம்", "language": "ta"}, timeout=60)
    audio = TtsResponse.model_validate(spoken.raise_for_status().json())
    heard = await http.post(
        f"{base}/stt",
        json={"audio_base64": audio.audio_base64, "mime_type": audio.mime_type},
        timeout=60,
    )
    SttResponse.model_validate(heard.raise_for_status().json())
    size = len(base64.b64decode(audio.audio_base64))
    return Result(name, READY, f"/translate, /tts and /stt answered, {size} bytes of audio")


async def check_browser(settings: Settings, http: httpx.AsyncClient) -> Result:
    name = "Browser service"
    base = settings.browser_product_url.rstrip("/")
    if not base:
        return Result(name, MISSING, "set BROWSER_PRODUCT_URL and BROWSER_PRODUCT_KEY")
    (await http.get(f"{base}/ready", timeout=20)).raise_for_status()
    portals = await http.get(
        f"{base}/integration/v1/portals",
        headers={"X-Internal-Key": settings.browser_product_key},
        timeout=20,
    )
    if portals.status_code in (401, 403):
        return Result(name, FAILED, "BROWSER_PRODUCT_KEY was refused")
    portals.raise_for_status()
    return Result(name, READY, "ready, and the key was accepted")


async def check_llm(settings: Settings, http: httpx.AsyncClient) -> Result:
    name = "AI model"
    if not settings.llm_base_url:
        return Result(name, MISSING, "set LLM_BASE_URL")
    response = await http.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "Reply with OK"}],
        },
        timeout=30,
    )
    response.raise_for_status()
    return Result(name, READY, settings.llm_model)


async def guarded(name: str, check: Callable[[], Awaitable[Result]], verbose: bool) -> Result:
    """A failing teammate module becomes a report line, not a crash."""
    try:
        return await check()
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:4]
        )
        return Result(name, FAILED, f"does not match contracts/: {issues}")
    except Exception as exc:
        if verbose:
            traceback.print_exc()
        return Result(name, FAILED, f"{type(exc).__name__}: {exc}"[:200])


async def check_modules(plugins: Plugins, document: Path | None, verbose: bool = False) -> list[Result]:
    checks: list[tuple[str, str, Callable | None, Callable[[Callable], Awaitable[Result]]]] = [
        ("Document extraction", "modules/extraction.py", plugins.extraction,
         lambda function: check_extraction(function, document)),
        ("Eligibility rule engine", "modules/rules.py", plugins.rules, check_rules),
        ("Application doctor", "modules/doctor.py", plugins.doctor, check_doctor),
        ("File compressor", "modules/compressor.py", plugins.compressor, check_compressor),
    ]
    results = []
    for name, path, function, check in checks:
        if function is None:
            results.append(Result(name, MISSING, f"add {path}"))
        else:
            results.append(await guarded(name, lambda f=function, c=check: c(f), verbose))
    return results


def report(results: list[Result]) -> bool:
    width = max(len(result.name) for result in results)
    for result in results:
        print(f"{result.status:8} {result.name:{width}}  {result.detail}")
    return not any(result.status == FAILED for result in results)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Check every plug-in point.")
    parser.add_argument("--document", type=Path, help="a real document for extraction")
    parser.add_argument("--verbose", action="store_true", help="print full error traces")
    arguments = parser.parse_args()

    settings = Settings()
    results = await check_modules(load_plugins(), arguments.document, arguments.verbose)
    async with httpx.AsyncClient() as http:
        for name, check in (
            ("Language service", check_language),
            ("Browser service", check_browser),
            ("AI model", check_llm),
        ):
            results.append(
                await guarded(name, lambda c=check: c(settings, http), arguments.verbose)
            )
    return 0 if report(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
