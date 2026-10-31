import re

import cv2
import numpy as np

from modules.extraction import ocr
from modules.extraction.mask import find_sensitive, mask_text, redact
from modules.extraction.ocr import OcrWord

from tests.remote_helpers import needs_tesseract


def _w(text, x, line=(1, 1, 1)):
    return OcrWord(text=text, conf=90, box=(x, 10, 60, 20), line_key=line)


def test_find_aadhaar_split_over_three_words():
    words = [_w("Aadhaar", 0), _w("1234", 100), _w("5678", 170), _w("9012", 240)]
    hits = find_sensitive(words)
    assert [(k, [w.text for w in g]) for k, g in hits] == [("aadhaar", ["1234", "5678", "9012"])]


def test_bank_account_needs_cue():
    assert find_sensitive([_w("Cert", 0), _w("123456789012345", 80)]) == []
    hits = find_sensitive([_w("A/c", 0), _w("No:", 50), _w("123456789012345", 100)])
    assert hits[0][0] == "bank_account"


def test_redact_returns_last4_only():
    img = np.full((60, 400, 3), 255, np.uint8)
    _, last4, _ = redact(img, [_w("1234", 100), _w("5678", 170), _w("9012", 240)])
    assert last4 == {"aadhaar": ["9012"]}


def test_mask_text():
    assert mask_text("UID 1234 5678 9012") == "UID XXXX XXXX 9012"
    assert mask_text("A/c No. 123456789012345") == "A/c No. XXXXXXXXXXX2345"
    assert mask_text("Cert No TN-5202310123") == "Cert No TN-5202310123"


@needs_tesseract
def test_redact_on_rendered_image_leaves_no_12_digit_run():
    img = np.full((200, 1000, 3), 255, np.uint8)
    cv2.putText(img, "Aadhaar 1234 5678 9012", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    out, last4, _ = redact(img, ocr.read_words(img))
    assert last4.get("aadhaar") == ["9012"]
    text = " ".join(w.text for w in ocr.read_words(out, min_conf=0))
    assert not re.search(r"\d{4}\s?\d{4}\s?\d{4}", text)


def test_black_box_leaves_no_trace():
    img = np.full((60, 400, 3), 200, np.uint8)
    out, _, _ = redact(img, [_w("1234", 100), _w("5678", 170), _w("9012", 240)])
    x0, y0, x1, y1 = 100 - 8, 10 - 8, 300 + 8, 30 + 8
    assert (out[y0:y1, x0:x1] == 0).all()          # solid black, not a blur
    assert (out[45:, :] == 200).all()              # nothing else touched


@needs_tesseract
def test_upright_turns_an_upside_down_page():
    from modules.extraction import preprocess
    page = np.full((1400, 1000, 3), 255, np.uint8)
    for i in range(14):
        cv2.putText(page, f"This is to certify that the applicant line {i}", (40, 80 + 90 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    _, turned = preprocess.upright(cv2.rotate(page, cv2.ROTATE_180))
    assert turned == 180
    _, turned = preprocess.upright(page)
    assert turned == 0
