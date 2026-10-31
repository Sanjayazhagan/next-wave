"""Shared normalisers for names, amounts and dates (Indian conventions)."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

_PUNCT = re.compile(r"[^\w\s/\-]", re.UNICODE)
_WS = re.compile(r"\s+")


def norm_text(s: str | None) -> str:
    """Casefold, NFKC, strip punctuation except / and -, collapse whitespace."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
           "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000}


def _words_to_int(s: str) -> int | None:
    tokens = re.findall(r"[a-z]+", s.lower())
    tokens = [t for t in tokens if t not in {"and", "rupees", "rs", "only", "inr", "per", "annum", "year"}]
    if not tokens or any(t not in _UNITS and t not in _SCALES for t in tokens):
        return None
    total, current = 0, 0
    for t in tokens:
        if t in _UNITS:
            current += _UNITS[t]
        elif t == "hundred":
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * _SCALES[t]
            current = 0
    return total + current


def norm_amount(s: str | int | float | None) -> int | None:
    """Parse rupee amounts: 'Rs. 2,50,000/-', '₹250000', '2.5 lakh', 'Two Lakh Fifty Thousand'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    text = unicodedata.normalize("NFKC", s).lower()
    text = text.replace("₹", " ").replace("rs.", " ").replace("rs", " ").replace("inr", " ")
    text = re.sub(r"/-", " ", text)
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|thousand|k)?\b", text)
    if m:
        num = float(m.group(1).replace(",", ""))
        unit = m.group(2)
        mult = {"thousand": 1_000, "k": 1_000}.get(unit or "", _SCALES.get(unit or "", 1))
        return int(round(num * mult))
    return _words_to_int(text)


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def norm_date(s: str | date | None) -> date | None:
    """Parse dates, day-first: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy, yyyy-mm-dd, '15 Aug 2005'."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = s.strip()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text):
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})[,\s\-]+(\d{4})", text):
            mon = _MONTHS.get(m[2][:3].lower())
            if mon:
                return date(int(m[3]), mon, int(m[1]))
    except ValueError:
        return None
    return None


# Social categories used by Tamil Nadu and central schemes.
CATEGORIES = ["SC", "SCA", "ST", "BC", "BCM", "MBC", "DNC", "OBC", "EWS", "OC", "GEN"]
_CATEGORY_ALIASES = {
    "scheduled caste arunthathiyar": "SCA", "arunthathiyar": "SCA", "sc arunthathiyar": "SCA",
    "scheduled caste": "SC", "scheduled castes": "SC",
    "scheduled tribe": "ST", "scheduled tribes": "ST",
    "backward class muslim": "BCM", "backward classes muslim": "BCM", "bc muslim": "BCM",
    "most backward class": "MBC", "most backward classes": "MBC",
    "denotified community": "DNC", "denotified communities": "DNC", "denotified tribes": "DNC",
    "backward class": "BC", "backward classes": "BC",
    "other backward class": "OBC", "other backward classes": "OBC",
    "economically weaker section": "EWS", "economically weaker sections": "EWS",
    "open competition": "OC", "general": "GEN", "forward community": "OC",
}


def norm_category(s: str | None) -> str | None:
    """Map a printed category ('Most Backward Class', 'B.C.', 'mbc') to its short code, else None."""
    if not s:
        return None
    t = norm_text(s).replace(".", "")
    compact = t.replace(" ", "").upper()
    if compact in CATEGORIES:
        return compact
    for alias in sorted(_CATEGORY_ALIASES, key=len, reverse=True):
        if alias in t:
            return _CATEGORY_ALIASES[alias]
    return None
