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


# Fields copied from print, where the model's small spelling slips can be checked against OCR.
PRINTED_FIELDS = {"full_name", "father_name", "mother_name", "district", "state", "institution"}
SNAP_MIN_RATIO = 80     # close enough to be the same word misspelt
SNAP_MIN_OCR_CONF = 85  # and Tesseract was sure of its reading


def snap_to_print(value: str, lines: list[OcrLine]) -> str:
    """Correct a model's small spelling slips ("Sathyajit" for printed "Satyajit", "Chengalpatu").

    Each word of the value is compared with confidently read OCR words on the line that best
    matches the whole value; a near match that differs is replaced by the printed spelling.
    Initials and words with no confident near match are left as the model read them.
    """
    if not value or not lines:
        return value
    needle = norm_text(value)
    line = max(lines, key=lambda ln: fuzz.partial_ratio(needle, norm_text(ln.text)))
    sure = [w for w in line.words if w.conf >= SNAP_MIN_OCR_CONF and w.text.strip(".,:;").isalpha()]
    out = []
    for token in value.split():
        bare = token.strip(".,")
        if len(bare) < 3 or not bare.isalpha():
            out.append(token)
            continue
        best = max(sure, key=lambda w: fuzz.ratio(bare.lower(), w.text.strip(".,:;").lower()), default=None)
        printed = best.text.strip(".,:;") if best else ""
        ratio = fuzz.ratio(bare.lower(), printed.lower()) if best else 0
        if SNAP_MIN_RATIO <= ratio < 100 and abs(len(printed) - len(bare)) <= 2:
            # Take the printed spelling, keep the model's casing (SATYAJIT / Satyajit).
            fixed = printed.upper() if bare.isupper() else printed.capitalize() if bare[0].isupper() else printed.lower()
            token = token.replace(bare, fixed)
        out.append(token)
    return " ".join(out)
