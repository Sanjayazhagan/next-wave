"""Confidence = agreement between the vision LLM and independent OCR, plus a validity check."""
from __future__ import annotations

from rapidfuzz import fuzz

from common.textnorm import norm_text

from . import validators
from .ocr import OcrLine, union_box

W_AGREE = 0.6
W_VALID = 0.4


def score(field: str, value: object, evidence: str | None, lines: list[OcrLine]) -> tuple[float, list[float] | None]:
    """Return (confidence 0..1, bbox [x, y, w, h] of the best OCR match or None)."""
    if value is None:
        return 0.0, None
    needle = norm_text(evidence or str(value))
    best, best_box = 0.0, None
    if needle:
        candidates = [(ln.text, ln.box) for ln in lines]
        # Values that wrap onto the next line.
        candidates += [(a.text + " " + b.text, union_box([a.box, b.box])) for a, b in zip(lines, lines[1:])]
        for text, box in candidates:
            r = fuzz.partial_ratio(needle, norm_text(text)) / 100
            if r > best:
                best, best_box = r, box
    valid = 1.0 if validators.check(field, value) else 0.0
    conf = round(W_AGREE * best + W_VALID * valid, 3)
    return conf, (list(map(float, best_box)) if best_box else None)
