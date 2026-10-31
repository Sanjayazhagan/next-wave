"""Fit a document file to a portal's limits while keeping it readable."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from contracts.portal import DocSpec, PreparedFile
from modules.extraction import preprocess

from . import legibility

Q_MIN, Q_MAX = 35, 95
SCALE_STEP = 0.85
MAX_WORK_SIDE = 2400   # about A4 at 200 dpi; no portal needs more
MIN_WIDTH = 800
PDF_OVERHEAD_KB = 8
MIMES = {"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png"}


class CannotFit(ValueError):
    def __init__(self, best_kb: float, max_kb: int) -> None:
        super().__init__(f"cannot fit under {max_kb} KB; best attempt was {best_kb:.0f} KB")
        self.best_kb = best_kb


@dataclass
class Result:
    data: bytes
    info: PreparedFile


def sniff(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def _accepted(spec: DocSpec) -> set[str]:
    return {"jpeg" if t in ("jpg", "jpeg") else t for t in spec.accepted_types}


def target_format(source: str | None, spec: DocSpec) -> str:
    """Keep the source format when the portal accepts it (core labels the upload with the
    original MIME type); otherwise PDF if it's the only option, else JPEG, else PNG."""
    ok = _accepted(spec)
    if source in ok:
        return source
    if ok == {"pdf"}:
        return "pdf"
    return "jpeg" if "jpeg" in ok else ("png" if "png" in ok else "pdf")


def _kb(b: bytes) -> float:
    return round(len(b) / 1024, 1)


def _fit_px(img: Image.Image, max_px: tuple[int, int] | None) -> Image.Image:
    if not max_px or (img.width <= max_px[0] and img.height <= max_px[1]):
        return img
    s = min(max_px[0] / img.width, max_px[1] / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def _encode(pages: list[Image.Image], fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()
    if fmt == "pdf":
        rgb = [p.convert("RGB") if p.mode not in ("RGB", "L") else p for p in pages]
        rgb[0].save(buf, "PDF", resolution=150.0, save_all=True, append_images=rgb[1:], quality=quality)
    elif fmt == "jpeg":
        pages[0].save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    else:
        pages[0].save(buf, "PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def _search_quality(pages: list[Image.Image], fmt: str, max_kb: float) -> tuple[bytes, int] | None:
    """Largest quality whose output is <= max_kb, by binary search. None if Q_MIN is still too big."""
    if fmt == "png":
        out = _encode(pages, fmt, 0)
        return (out, 0) if _kb(out) <= max_kb else None
    lo, hi, best = Q_MIN, Q_MAX, None
    while lo <= hi:
        q = (lo + hi) // 2
        out = _encode(pages, fmt, q)
        if _kb(out) <= max_kb:
            best, lo = (out, q), q + 1
        else:
            hi = q - 1
    return best


def _load(data: bytes, source: str | None, actions: list[str]) -> list[np.ndarray]:
    pages = preprocess.load_pages(data, "application/pdf" if source == "pdf" else None)
    if source == "pdf":
        return pages
    # Photos: crop to the paper and straighten, as extraction does.
    out = []
    for p in pages:
        cropped, found = preprocess.find_document(p)
        if found:
            actions.append("cropped")
        straight, angle = preprocess.deskew(cropped)
        if 0.5 < abs(angle) < 15:
            actions.append(f"deskewed {abs(angle):.1f}°")
        out.append(straight)
    return out


def _render_first(data: bytes, fmt: str) -> np.ndarray:
    return preprocess.load_pages(data, "application/pdf" if fmt == "pdf" else None)[0]


def prepare(data: bytes, spec: DocSpec, check_legibility: bool = True) -> Result:
    """Return bytes the portal accepts plus a PreparedFile describing what was done."""
    source = sniff(data)
    fmt = target_format(source, spec)
    actions: list[str] = []
    before_kb = _kb(data)

    if source == fmt and before_kb <= spec.max_kb and (spec.min_kb is None or before_kb >= spec.min_kb):
        pages_np = preprocess.load_pages(data, "application/pdf" if fmt == "pdf" else None)
        h, w = pages_np[0].shape[:2]
        if spec.max_px is None or (w <= spec.max_px[0] and h <= spec.max_px[1]):
            return Result(data, PreparedFile(mime=MIMES[fmt], size_kb=before_kb, px=(w, h), pages=len(pages_np),
                                             actions=["already within portal limits"], legible=True,
                                             words_before=None, words_after=None))

    pages_np = _load(data, source, actions)
    if source != fmt:
        actions.append(f"converted to {fmt.upper()}")
    pages = [Image.fromarray(p) for p in pages_np]
    w0, h0 = pages[0].size
    pages = [_fit_px(_fit_px(p, (MAX_WORK_SIDE, MAX_WORK_SIDE)), spec.max_px) for p in pages]

    budget = spec.max_kb - (PDF_OVERHEAD_KB if fmt == "pdf" else 0)
    found = _search_quality(pages, fmt, budget)
    best_kb = float("inf")
    while found is None and pages[0].width > MIN_WIDTH:
        kb_at_min = _kb(_encode(pages, fmt, Q_MIN))
        best_kb = min(best_kb, kb_at_min)
        # File size grows roughly with pixel count: jump close to the target in one step.
        scale = min(SCALE_STEP, math.sqrt(budget / kb_at_min) * 0.95)
        width = max(MIN_WIDTH, int(pages[0].width * scale))
        scale = width / pages[0].width
        pages = [p.resize((width, max(1, int(p.height * scale))), Image.LANCZOS) for p in pages]
        found = _search_quality(pages, fmt, budget)
    if pages[0].size != (w0, h0):
        actions.append(f"resized {w0}x{h0} to {pages[0].width}x{pages[0].height}")
    if found is None:
        gray = [p.convert("L") for p in pages]
        found = _search_quality(gray, fmt, budget)
        if found is None:
            raise CannotFit(min(best_kb, _kb(_encode(gray, fmt, Q_MIN))), spec.max_kb)
        pages = gray
        actions.append("converted to grayscale")
    out, q = found

    if spec.min_kb and _kb(out) < spec.min_kb:
        for q2 in range(q + 5, Q_MAX + 1, 5):
            out2 = _encode(pages, fmt, q2)
            if _kb(out2) > budget:
                break
            out, q = out2, q2
            if _kb(out) >= spec.min_kb:
                break
        if _kb(out) < spec.min_kb:
            actions.append("below portal minimum size, check manually")
    actions.append(f"{before_kb:.0f} KB to {_kb(out):.0f} KB" + (f" (quality {q})" if fmt != "png" else ""))

    legible, wb, wa = True, None, None
    if check_legibility and legibility.available():
        legible, wb, wa = legibility.check(pages_np[0], _render_first(out, fmt))
    elif check_legibility:
        actions.append("legibility not checked (tesseract not installed)")
    return Result(out, PreparedFile(mime=MIMES[fmt], size_kb=_kb(out), px=pages[0].size, pages=len(pages),
                                    actions=actions, legible=legible, words_before=wb, words_after=wa))
