"""Put the doctor's findings into the chat's language.

Headings come from a fixed table for Tamil and Hindi, the languages core ships built in.
Fix sentences go through the language service (LANGUAGE_SERVICE_URL), with the values a
user must see unchanged (quoted names, scheme names, certificate numbers, links) kept out of
translation. If the service isn't set or fails, the readable English is returned.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from common.config import env

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 15

HEADINGS = {
    "ta": {"Name": "பெயர்", "Father's name": "தந்தையின் பெயர்", "Mother's name": "தாயின் பெயர்",
           "Date of birth": "பிறந்த தேதி", "Community": "சமூகம்", "Family income": "குடும்ப வருமானம்",
           "Eligibility": "தகுதி", "Missing document": "இல்லாத ஆவணம்", "Documents": "ஆவணங்கள்",
           "Marksheet": "மதிப்பெண் பட்டியல்", "Income certificate": "வருமானச் சான்றிதழ்",
           "Community certificate": "சமூகச் சான்றிதழ்"},
    "hi": {"Name": "नाम", "Father's name": "पिता का नाम", "Mother's name": "माता का नाम",
           "Date of birth": "जन्म तिथि", "Community": "समुदाय", "Family income": "पारिवारिक आय",
           "Eligibility": "पात्रता", "Missing document": "छूटा हुआ दस्तावेज़", "Documents": "दस्तावेज़",
           "Marksheet": "अंकपत्र", "Income certificate": "आय प्रमाणपत्र",
           "Community certificate": "जाति प्रमाणपत्र"},
}
KEEP_ALWAYS = ["TN e-District", "tnedistrict.tn.gov.in", "e-Sevai", "OBC", "BC", "MBC", "DNC"]
_QUOTED = re.compile(r"'([^']+)'")
_LINK = re.compile(r"\b[\w-]+(?:\.[\w-]+)+\b")


def _keep(text: str, extra: list[str]) -> list[str]:
    return list(dict.fromkeys([*_QUOTED.findall(text), *_LINK.findall(text), *extra, *KEEP_ALWAYS]))


def _translate(text: str, language: str, keep: list[str], url: str) -> str:
    try:
        r = httpx.post(f"{url.rstrip('/')}/translate", timeout=TIMEOUT_SECONDS,
                       json={"text": text, "source": "en", "target": language, "keep": keep})
        r.raise_for_status()
        return r.json()["text"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("Doctor finding left in English: %s", type(exc).__name__)
        return text


def localize(findings: list[tuple[str, str]], language: str, keep: list[str] | None = None) -> list[tuple[str, str]]:
    """[(heading, fix)] in English -> the same in `language`."""
    language = (language or "en").lower()
    if language == "en" or not findings:
        return findings
    url = env("LANGUAGE_SERVICE_URL")
    table = HEADINGS.get(language, {})

    def one(pair: tuple[str, str]) -> tuple[str, str]:
        head, fix = pair
        if url:
            fix = _translate(fix, language, _keep(fix, keep or []), url)
            if head not in table:
                head = _translate(head, language, [], url)
        return table.get(head, head), fix

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(one, findings))
