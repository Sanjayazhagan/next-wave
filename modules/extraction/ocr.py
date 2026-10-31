"""Independent OCR with Tesseract, grouped into lines with boxes."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pytesseract

log = logging.getLogger(__name__)
MIN_CONF = 30


@dataclass
class OcrWord:
    text: str
    conf: float
    box: tuple[int, int, int, int]   # x, y, w, h
    line_key: tuple[int, int, int]   # (block, par, line)


@dataclass
class OcrLine:
    text: str
    box: tuple[int, int, int, int]
    words: list[OcrWord]


@lru_cache(maxsize=1)
def ocr_lang() -> str:
    """'eng+tam' when the Tamil pack is installed, else 'eng' (logged once)."""
    langs = set(pytesseract.get_languages(config=""))
    if "tam" in langs:
        return "eng+tam"
    log.warning("tesseract-ocr-tam not installed; OCR runs English only")
    return "eng"


def read_words(img: np.ndarray, min_conf: float = MIN_CONF) -> list[OcrWord]:
    """Words with confidence above `min_conf`."""
    d = pytesseract.image_to_data(img, lang=ocr_lang(), output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(d["text"]):
        conf = float(d["conf"][i])
        if text.strip() and conf > min_conf:
            words.append(OcrWord(text=text.strip(), conf=conf,
                                 box=(d["left"][i], d["top"][i], d["width"][i], d["height"][i]),
                                 line_key=(d["block_num"][i], d["par_num"][i], d["line_num"][i])))
    return words


def union_box(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return x0, y0, x1 - x0, y1 - y0


def group_lines(words: list[OcrWord]) -> list[OcrLine]:
    """Group words into lines by Tesseract's (block, paragraph, line) numbers, in reading order."""
    groups: dict[tuple[int, int, int], list[OcrWord]] = {}
    for w in words:
        groups.setdefault(w.line_key, []).append(w)
    return [OcrLine(text=" ".join(w.text for w in ws), box=union_box([w.box for w in ws]), words=ws)
            for _, ws in sorted(groups.items())]


def read(img: np.ndarray) -> list[OcrLine]:
    return group_lines(read_words(img))
