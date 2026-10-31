"""Load photos/PDFs, find the document, deskew, and measure image quality."""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from . import ocr as _ocr  # noqa: F401  (sets Tesseract's thread limit)
from .models import Quality

register_heif_opener()

# Tuned on fixtures; see README for the final values.
BLUR_MIN = 60.0
BRIGHTNESS_MIN = 60.0
PDF_SCALE = 200 / 72


def load_pages(src: Path | bytes, mime_type: str | None = None) -> list[np.ndarray]:
    """Return RGB uint8 arrays, one per page. Applies EXIF rotation; renders PDFs at 200 dpi."""
    data = src if isinstance(src, bytes) else Path(src).read_bytes()
    is_pdf = data[:5] == b"%PDF-" or (mime_type or "").endswith("pdf")
    if is_pdf:
        pdf = pdfium.PdfDocument(data)
        try:
            return [np.array(page.render(scale=PDF_SCALE).to_pil().convert("RGB")) for page in pdf]
        finally:
            pdf.close()
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        return [np.array(im.convert("RGB"))]


def _gray_1000(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    return cv2.resize(gray, (1000, max(1, int(h * 1000 / w))), interpolation=cv2.INTER_AREA)


def quality(img: np.ndarray, skew_deg: float = 0.0) -> Quality:
    """Blur (variance of Laplacian) and brightness measured at 1000 px width."""
    gray = _gray_1000(img)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    bright = float(gray.mean())
    return Quality(blur_score=round(blur, 1), brightness=round(bright, 1), skew_deg=round(skew_deg, 2),
                   too_blurry=blur < BLUR_MIN, too_dark=bright < BRIGHTNESS_MIN)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def find_document(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Crop to the paper with a perspective transform if a large 4-sided contour is found."""
    h, w = img.shape[:2]
    scale = 800 / h
    small = cv2.resize(img, (max(1, int(w * scale)), 800), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), None, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_min = 0.25 * small.shape[0] * small.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(approx) > area_min:
            src = _order_corners(approx.reshape(4, 2).astype(np.float32) / scale)
            tl, tr, br, bl = src
            out_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            out_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
            m = cv2.getPerspectiveTransform(src, dst)
            return cv2.warpPerspective(img, m, (out_w, out_h)), True
    return img, False


_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


UPRIGHT_ENOUGH = 10   # confident words that settle "already upright" without trying other turns


def _readable_words(img: np.ndarray) -> int:
    """Confident words when read as one block of horizontal text. Tesseract's default mode
    also reads sideways text, so it can't tell the orientations apart; this mode can."""
    d = pytesseract.image_to_data(img, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT)
    return sum(1 for t, c in zip(d["text"], d["conf"]) if len(t.strip()) >= 3 and t.strip().isalpha() and float(c) > 70)


def upright(img: np.ndarray) -> tuple[np.ndarray, int]:
    """Turn a sideways or upside-down photo upright. Returns (image, degrees rotated clockwise).

    Tesseract's own orientation detection is unreliable on photocopies, so each of the four
    orientations of a small copy is read and the one with the most confident words wins.
    Masking depends on this: upside-down digits aren't recognised, so they can't be blacked out.
    """
    h, w = img.shape[:2]
    scale = min(1.0, 1000 / max(h, w))  # smaller copies of faint photocopies give too few words
    small = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    try:
        scores = {0: _readable_words(small)}
        if scores[0] >= UPRIGHT_ENOUGH:
            return img, 0
        scores.update({deg: _readable_words(cv2.rotate(small, code)) for deg, code in _ROTATIONS.items()})
    except pytesseract.TesseractError:
        return img, 0
    best = max(scores, key=scores.get)
    if best == 0 or scores[best] <= scores[0] * 1.2:
        return img, 0
    return cv2.rotate(img, _ROTATIONS[best]), best


def measure_skew(img: np.ndarray) -> float:
    """Angle in degrees of the text block (positive = counter-clockwise tilt)."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    if gray.shape[1] > 1200:  # the angle doesn't depend on resolution; measure on a small copy
        gray = cv2.resize(gray, (1200, int(gray.shape[0] * 1200 / gray.shape[1])), interpolation=cv2.INTER_AREA)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(th > 0))[:, ::-1].astype(np.float32)  # (x, y)
    if len(coords) < 50:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    # minAreaRect uses image coords (y down); flip so positive means counter-clockwise.
    return -float(angle)


def deskew(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Rotate the image upright when 0.5° < |skew| < 15°. Returns (image, skew_deg)."""
    angle = measure_skew(img)
    if not 0.5 < abs(angle) < 15:
        return img, angle
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, angle
