"""Does the compressed file still read? Compare confident OCR words before and after."""
from __future__ import annotations

import shutil

import numpy as np
import pytesseract

MIN_CONF = 60
MIN_WORDS = 10      # below this the page has too little text to judge
KEEP_RATIO = 0.8


def available() -> bool:
    return shutil.which("tesseract") is not None


def word_count(img: np.ndarray) -> int:
    d = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
    return sum(1 for t, c in zip(d["text"], d["conf"]) if t.strip() and float(c) > MIN_CONF)


def check(before: np.ndarray, after: np.ndarray) -> tuple[bool, int, int]:
    """Return (legible, words_before, words_after)."""
    wb = word_count(before)
    wa = word_count(after)
    if wb < MIN_WORDS:
        return True, wb, wa
    return wa >= KEEP_RATIO * wb, wb, wa
