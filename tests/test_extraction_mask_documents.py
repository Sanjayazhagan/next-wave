"""The mask on real documents: fake ID numbers planted on every fixture, in several photo
conditions. Nothing readable may survive. Needs tesseract and fixtures/docs (skips otherwise)."""
import re

import cv2
import numpy as np
import pytest
import pytesseract

from modules.extraction import ocr, preprocess
from modules.extraction.mask import redact
from tests.remote_helpers import FIXTURES, needs_tesseract

DOCS = sorted((FIXTURES / "docs").glob("*.pdf")) + sorted((FIXTURES / "docs").glob("*.jpg")) \
    if (FIXTURES / "docs").is_dir() else []
# Fake numbers in the formats certificates and passbooks use (test data only).
PLANTED = [("Aadhaar No: 4821 7365 9012", "aadhaar"), ("UID: 5930-2846-1177", "aadhaar"),
           ("SB A/c No: 31245678901234", "bank")]
LEAKS = [re.compile(r"4821\D{0,3}7365\D{0,3}9012"), re.compile(r"5930\D{0,3}2846\D{0,3}1177"),
         re.compile(r"3124567890\d{0,4}|5678901234")]
CONDITIONS = {
    "upright": lambda im: im,
    "upside_down": lambda im: cv2.rotate(im, cv2.ROTATE_180),
    "sideways": lambda im: cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE),
    "low_quality": lambda im: cv2.imdecode(cv2.imencode(".jpg", cv2.resize(cv2.resize(im, None, fx=0.45, fy=0.45),
                                           (im.shape[1], im.shape[0])), [cv2.IMWRITE_JPEG_QUALITY, 25])[1],
                                           cv2.IMREAD_COLOR),
}


def _plant(page: np.ndarray) -> np.ndarray:
    page = page.copy()
    h, w = page.shape[:2]
    y = int(h * 0.62)
    cv2.rectangle(page, (int(w * 0.07), y - 40), (int(w * 0.75), y + 3 * 55), (255, 255, 255), -1)
    for i, (text, _) in enumerate(PLANTED):
        cv2.putText(page, text, (int(w * 0.08), y + i * 55), cv2.FONT_HERSHEY_SIMPLEX, w / 1550, (30, 30, 30), 2)
    return page


def _readable(img: np.ndarray) -> str:
    return " ".join(pytesseract.image_to_string(img if r is None else cv2.rotate(img, r), config="--psm 11")
                    for r in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE))


@needs_tesseract
@pytest.mark.live
@pytest.mark.skipif(not DOCS, reason="no fixtures/docs")
@pytest.mark.parametrize("condition", list(CONDITIONS))
@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.stem)
def test_planted_numbers_are_blacked_out(doc, condition):
    page = _plant(preprocess.load_pages(doc.read_bytes())[0])
    img, _ = preprocess.upright(CONDITIONS[condition](page))
    img, _ = preprocess.find_document(img)
    img, _ = preprocess.deskew(img)
    out, last4, _ = redact(img, ocr.read_words(img))
    assert sorted(last4.get("aadhaar", [])) == ["1177", "9012"] and last4.get("bank_account") == ["1234"]
    text = _readable(out).replace(" ", "")
    assert not any(p.search(text) for p in LEAKS), "a planted number is still readable"
