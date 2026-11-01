"""Read a correction to the draft application, in code (never through an AI model).

The review lists what was filled as "N. <label>: value". A user may reply "2 120000",
"2. 120000", "income 2 lakh", "date of birth 15/08/2005", "change father's name to
K Subramanian", or use the portal's own label. Values are converted to the profile's
formats (income as digits, date of birth as DD-MM-YYYY). Anything that can't be placed
or converted returns None, so the user is asked again rather than guessed at.
"""
from __future__ import annotations

import re

from .textnorm import norm_amount, norm_category, norm_date, norm_text, strip_honorifics

ALIASES = {
    "full_name": ["full name", "applicant name", "student name", "my name", "name"],
    "father_name": ["father's name", "fathers name", "father name", "father"],
    "mother_name": ["mother's name", "mothers name", "mother name", "mother"],
    "date_of_birth": ["date of birth", "birth date", "dob", "born"],
    "annual_income": ["annual family income", "family income", "annual income", "yearly income", "income", "salary"],
    "community": ["community category", "community", "category", "caste"],
    "gender": ["gender", "sex"],
    "state": ["state"],
    "district": ["district"],
    "course": ["course", "programme", "studying"],
    "marks_percentage": ["marks percentage", "percentage", "marks", "percent"],
}
LEAD = re.compile(r"^(please\s+)?(change|set|update|correct|fix|make|edit)?\s*(my|the)?\s*", re.I)
JOIN = re.compile(r"^\s*(:|-|=|is\b|to\b|should be\b|as\b)?\s*", re.I)
NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.):\-]?\s+(.+)$", re.S)
UNIT_ONLY = re.compile(r"^\s*(lakh|lakhs|lac|thousand|k|crore)\b", re.I)
NAME = re.compile(r"^[A-Za-z][A-Za-z .']{1,59}$")
GENDER = {"female": "Female", "f": "Female", "girl": "Female", "woman": "Female",
          "male": "Male", "m": "Male", "boy": "Male", "man": "Male",
          "transgender": "Transgender", "other": "Transgender"}


def normalize(field: str, raw: str) -> str | None:
    """The value in the profile's format, or None if it isn't a believable value for the field."""
    raw = raw.strip().strip(".")
    if not raw:
        return None
    if field == "annual_income":
        amount = norm_amount(raw)
        return str(amount) if amount is not None and 0 <= amount <= 100_000_000 else None
    if field == "date_of_birth":
        d = norm_date(raw)
        return d.strftime("%d-%m-%Y") if d and 1940 <= d.year <= 2015 else None
    if field == "marks_percentage":
        m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*%?", raw)
        return m[1] if m and 0 <= float(m[1]) <= 100 else None
    if field in ("full_name", "father_name", "mother_name"):
        name = strip_honorifics(raw)
        return name if NAME.match(name) else None
    if field == "community":
        return norm_category(raw) or None
    if field == "gender":
        return GENDER.get(norm_text(raw))
    return raw if len(raw) <= 100 else None


def _by_label(text: str, filled: dict[str, dict]) -> tuple[str, str] | None:
    """Match the longest field label or alias at the start of the text."""
    wanted = LEAD.sub("", text.strip())
    lowered = wanted.lower()
    options = []
    for field, details in filled.items():
        names = ALIASES.get(field, []) + [str(details.get("label", "")).lower()]
        options += [(name.lower(), field) for name in names if name]
    for name, field in sorted(options, key=lambda o: len(o[0]), reverse=True):
        if lowered.startswith(name) and (len(lowered) == len(name) or not lowered[len(name)].isalnum()):
            value = JOIN.sub("", wanted[len(name):], count=1).strip()
            return (field, value) if value else None
    return None


def parse_draft_edit(text: str, filled: dict[str, dict]) -> tuple[str, str] | None:
    """Return (field, raw value) for a correction to the filled fields, or None.

    `filled` is core's state["filled"]: field -> {"label": ...}, in the order the review numbers them.
    """
    fields = list(filled)
    numbered = NUMBERED.match(text.strip())
    if numbered and not UNIT_ONLY.match(numbered[2]):   # "2 lakh" is money, not item 2
        index = int(numbered[1])
        return (fields[index - 1], numbered[2].strip()) if 1 <= index <= len(fields) else None
    labelled = _by_label(text, filled)
    if labelled:
        return labelled
    if "annual_income" in filled and norm_amount(text) is not None and re.search(r"lakh|lac|₹|rs|thousand", text, re.I):
        return "annual_income", text.strip()
    return None
