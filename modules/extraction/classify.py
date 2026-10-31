"""Document type classification (only used when the caller doesn't pass doc_type)."""
from __future__ import annotations

import cv2
import numpy as np

from common.llm import vision_json
from .models import DocType

from .prompts import CLASSIFY, SYSTEM
from .schemas import DocTypeAnswer


def jpeg_bytes(img: np.ndarray, max_side: int = 2000, quality: int = 90) -> bytes:
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def classify(img: np.ndarray) -> DocType:
    return vision_json([jpeg_bytes(img)], CLASSIFY, DocTypeAnswer, caller="extraction.classify",
                       system=SYSTEM).doc_type
