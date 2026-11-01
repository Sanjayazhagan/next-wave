"""Black out Aadhaar and bank account numbers before anything is saved or sent to an LLM."""
from __future__ import annotations

import re

import numpy as np

from .ocr import OcrWord, union_box

_DIGITS = re.compile(r"^\d+$")
_ACCOUNT_CUE = re.compile(r"^(a/?c|acc(oun)?t|acct|sb|a/c\.?|account)[:.]?$", re.I)
_AADHAAR_TEXT = re.compile(r"(?<!\d)(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})(?!\d)")
_ACCOUNT_TEXT = re.compile(r"((?:a/?c|acc(?:oun)?t|acct|sb)\b[^\d]{0,15})(\d{5,14})(\d{4})(?!\d)", re.I)


def _black_out(img: np.ndarray, box: tuple[int, int, int, int], pad: int = 8) -> None:
    """A solid black box: unlike a blur, nothing of the digits survives for a model to recover."""
    x, y, w, h = box
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = 0


def find_sensitive(words: list[OcrWord]) -> list[tuple[str, list[OcrWord]]]:
    """Return (kind, words) for each Aadhaar (12 digits, maybe split over 3 words) or bank account."""
    hits: list[tuple[str, list[OcrWord]]] = []
    used: set[int] = set()
    for i in range(len(words)):
        for n in (1, 2, 3):
            group = words[i:i + n]
            if len(group) < n or any(id(w) in used for w in group):
                continue
            if len({w.line_key for w in group}) > 1:
                continue
            joined = "".join(w.text.replace("-", "") for w in group)
            if all(_DIGITS.match(w.text.replace("-", "")) for w in group) and len(joined) == 12:
                hits.append(("aadhaar", group))
                used.update(id(w) for w in group)
                break
    for i, w in enumerate(words):
        t = w.text.replace("-", "")
        if id(w) in used or not (_DIGITS.match(t) and 9 <= len(t) <= 18):
            continue
        context = [c for c in words[max(0, i - 4):i] if c.line_key == w.line_key]
        if any(_ACCOUNT_CUE.match(c.text) for c in context):
            hits.append(("bank_account", [w]))
            used.add(id(w))
    return hits


def redact(img: np.ndarray, words: list[OcrWord]) -> tuple[np.ndarray, dict[str, list[str]], list[OcrWord]]:
    """Black out sensitive numbers on a copy.

    Returns (image, {kind: [last4, ...]}, the OCR words that were not masked).
    """
    out = img.copy()
    last4s: dict[str, list[str]] = {}
    masked: set[int] = set()
    for kind, group in find_sensitive(words):
        _black_out(out, union_box([w.box for w in group]))
        digits = "".join(w.text.replace("-", "") for w in group)
        last4s.setdefault(kind, []).append(digits[-4:])
        masked.update(id(w) for w in group)
    return out, last4s, [w for w in words if id(w) not in masked]


def mask_text(s: str | None) -> str | None:
    """Text-level guard: keep only the last 4 digits of Aadhaar-like and account numbers."""
    if s is None:
        return None
    s = _AADHAAR_TEXT.sub(lambda m: "XXXX XXXX " + m.group(3), s)
    return _ACCOUNT_TEXT.sub(lambda m: m.group(1) + "X" * len(m.group(2)) + m.group(3), s)
