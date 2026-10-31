"""Read the QR code printed on TN e-District certificates.

The QR holds the original application/certificate number, the applicant's name
and the service. If someone edits the printed text, the QR still holds the
original, so the doctor compares the two (modules/doctor/checks.authenticity).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

from common.textnorm import norm_text

from .mask import mask_text

# QR payload keys (normalised) -> our names.
KEYS = {
    "application no": "certificate_number", "certificate no": "certificate_number", "certificate number": "certificate_number",
    "applicant name": "name", "name": "name",
    "service applied": "service", "service": "service",
}


@dataclass
class QrResult:
    status: Literal["decoded", "unreadable", "absent"]
    values: dict[str, str] = field(default_factory=dict)


def parse(text: str) -> dict[str, str]:
    """'Application No. : TN-62026...\\nApplicant Name : Satyajit' -> {certificate_number, name, ...}"""
    out = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = KEYS.get(norm_text(key).rstrip(" ."))
        if name and value.strip():
            out[name] = mask_text(value.strip())
    return out


def _attempts(page: np.ndarray):
    gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY) if page.ndim == 3 else page
    h, w = gray.shape
    yield gray
    yield cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    # The QR usually sits in a bottom corner; a zoomed crop helps small codes.
    for x0, x1 in ((0, w // 2), (w // 2, w)):
        crop = gray[h // 2:, x0:x1]
        yield cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def read_qr(pages: list[np.ndarray]) -> QrResult:
    detector = cv2.QRCodeDetector()
    located = False
    for page in pages:
        for img in _attempts(page):
            text, points, _ = detector.detectAndDecode(img)
            if text:
                values = parse(text)
                return QrResult("decoded", values) if values else QrResult("unreadable")
            located = located or points is not None
    return QrResult("unreadable" if located else "absent")
