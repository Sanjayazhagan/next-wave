"""Keep amounts, dates, IDs and named terms intact through machine translation.

mask() swaps them for tokens ⟦0⟧, ⟦1⟧ ... before translating; unmask() puts them back.
"""
from __future__ import annotations

import re

_PATTERNS = [
    # Rupee amounts: ₹2,50,000 / Rs. 2,50,000/- / INR 12000
    re.compile(r"(?:₹|Rs\.?|INR)\s?\d[\d,]*(?:\.\d+)?(?:/-)?", re.I),
    # Dates: 31/12/2026, 31-12-2026, 2026-12-31
    re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"),
    # ID-like tokens mixing letters and digits: TN-520231012, NSP2026X
    re.compile(r"\b(?=[A-Za-z0-9\-]*\d)(?=[A-Za-z0-9\-]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b|\b(?=\w*\d)(?=\w*[A-Za-z])[A-Z0-9]{5,}\b"),
    # Numbers with Indian digit grouping: 2,50,000
    re.compile(r"\b\d{1,3}(?:,\d{2})*,\d{3}\b"),
]


def token(i: int) -> str:
    return f"⟦{i}⟧"


def mask(text: str, keep: list[str] | None = None) -> tuple[str, list[str]]:
    """Return (masked text, originals by token index)."""
    originals: list[str] = []

    def swap(m: re.Match) -> str:
        originals.append(m.group())
        return token(len(originals) - 1)

    for term in sorted(keep or [], key=len, reverse=True):
        if term.strip():
            text = re.sub(re.escape(term), swap, text, flags=re.I)
    for pattern in _PATTERNS:
        text = pattern.sub(swap, text)
    return text, originals


_TOKEN = re.compile(r"⟦\s*(\d+)\s*⟧")


def unmask(text: str, originals: list[str]) -> tuple[str, list[str]]:
    """Return (text with originals restored, originals whose token went missing)."""
    seen: set[int] = set()

    def back(m: re.Match) -> str:
        i = int(m.group(1))
        if i < len(originals):
            seen.add(i)
            return originals[i]
        return m.group()

    restored = _TOKEN.sub(back, text)
    return restored, [o for i, o in enumerate(originals) if i not in seen]
