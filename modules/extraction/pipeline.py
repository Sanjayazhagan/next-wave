"""Pages of one document -> DocResult (typed values, OCR-agreement confidence)."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from common.config import env
from common.llm import vision_json
from common.textnorm import norm_amount, norm_category, norm_date, strip_honorifics

from . import confidence, ocr, preprocess
from .qr import read_qr
from .encode import jpeg_bytes
from .mask import mask_text, redact
from .models import DocResult, DocType, FieldRead, Quality
from .prompts import SYSTEM, extract_prompt, retry_prompt
from .schemas import FIELDS_BY_TYPE, HELPER_FIELDS, Read, doc_type_of, schema_for, shape

log = logging.getLogger(__name__)
RETRY_BELOW = 0.6
RETRY_PAD = 40
MAX_IMAGES = 3   # Groq's vision models take at most 3 images per request


def max_pages() -> int:
    """Pages read per document. Certificates and marksheets carry their details on page 1, and
    each extra page costs about 2,500 tokens of a tight per-minute and per-day allowance."""
    try:
        return max(1, min(MAX_IMAGES, int(env("EXTRACTION_MAX_PAGES", "1"))))
    except ValueError:
        return 1


@dataclass
class _Page:
    img: np.ndarray
    lines: list[ocr.OcrLine]
    quality: Quality


def typed(field: str, raw: str | None) -> object:
    """Convert the model's string to the field's type. None if it can't be parsed."""
    if raw is None or not str(raw).strip():
        return None
    raw = str(raw).strip()
    if field in ("date_of_birth", "issue_date", "valid_until"):
        return norm_date(raw)
    if field in ("full_name", "father_name", "mother_name"):
        return strip_honorifics(raw)
    if field == "annual_income":
        return norm_amount(raw)
    if field in ("marks_percentage", "marks_total", "marks_max"):
        m = re.search(r"\d+(?:\.\d+)?", raw)
        return float(m.group()) if m else None
    if field == "exam_year":
        m = re.search(r"(19|20)\d{2}", raw)
        return int(m.group()) if m else None
    if field == "community":
        return norm_category(raw) or raw
    return raw


def _clean_page(raw: np.ndarray) -> tuple[_Page, dict[str, list[str]]]:
    img, _ = preprocess.upright(raw)
    img, _ = preprocess.find_document(img)
    img, skew = preprocess.deskew(img)
    words = ocr.read_words(img)
    # Mask before saving and before any LLM call: the model never sees a full number.
    img, last4s, kept = redact(img, words)
    return _Page(img=img, lines=ocr.group_lines(kept), quality=preprocess.quality(img, skew)), last4s


def _save(pages: list[np.ndarray], doc_id: str) -> str:
    work = Path(env("WORK_DIR", "./work"))
    work.mkdir(parents=True, exist_ok=True)
    ims = [Image.fromarray(p) for p in pages]
    if len(ims) == 1:
        path = work / f"{doc_id}.jpg"
        ims[0].save(path, "JPEG", quality=92)
    else:
        path = work / f"{doc_id}.pdf"
        ims[0].save(path, "PDF", resolution=200.0, save_all=True, append_images=ims[1:])
    return str(path)


def _retry_field(page: _Page, doc_type: str, field: str, bbox: list[float]) -> Read:
    x, y, w, h = (int(v) for v in bbox)
    H, W = page.img.shape[:2]
    crop = page.img[max(0, y - RETRY_PAD):min(H, y + h + RETRY_PAD), max(0, x - RETRY_PAD):min(W, x + w + RETRY_PAD)]
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return vision_json([jpeg_bytes(crop)], retry_prompt(doc_type, field), Read, caller="extraction.retry", system=SYSTEM)


def _best_page(pages: list[_Page], value: object, evidence: str | None) -> _Page:
    """Bboxes are per page: pick the page whose OCR best matches the field."""
    return max(pages, key=lambda p: confidence.score("_", value, evidence, p.lines)[0])


def field_retry_on() -> bool:
    """Zoomed re-reads of weak fields cost one image call each, so they're off unless asked for."""
    return env("EXTRACTION_FIELD_RETRY", "0") == "1"


def extract_pages(raw_pages: list[np.ndarray], doc_type: DocType | None = None, doc_id: str | None = None,
                  retry: bool | None = None) -> DocResult:
    """Extract one document from its page images: one model call, which also decides the type
    when `doc_type` isn't given."""
    retry = field_retry_on() if retry is None else retry
    if not raw_pages:
        raise ValueError("no pages to extract")
    qr_pages = raw_pages   # the QR check is cheap, so it looks at every page
    if len(raw_pages) > max_pages():
        log.info("Document has %d pages; reading the first %d", len(raw_pages), max_pages())
        raw_pages = raw_pages[:max_pages()]
    t0 = time.perf_counter()
    doc_id = doc_id or uuid.uuid4().hex[:12]
    pages: list[_Page] = []
    last4s: dict[str, list[str]] = {}
    for raw in raw_pages:
        page, found = _clean_page(raw)
        pages.append(page)
        for k, v in found.items():
            last4s.setdefault(k, []).extend(v)
    masked_ref = _save([p.img for p in pages], doc_id)

    reads: dict[str, tuple[object, str | None, float, list[float] | None]] = {}
    answer = vision_json([jpeg_bytes(p.img) for p in pages], extract_prompt(doc_type),
                         schema_for(doc_type), caller="extraction.extract", system=SYSTEM, shape=shape(doc_type))
    if doc_type is None:
        doc_type = doc_type_of(answer.doc_type)
    if doc_type in FIELDS_BY_TYPE:
        all_lines = [ln for p in pages for ln in p.lines]
        for name in FIELDS_BY_TYPE[doc_type]:
            # Models send null for a field that isn't printed, such as a missing date.
            r: Read = getattr(answer, name) or Read()
            value, evidence = typed(name, mask_text(r.value)), mask_text(r.evidence)
            if name in confidence.PRINTED_FIELDS and isinstance(value, str):
                value = confidence.snap_to_print(value, all_lines)
            conf, bbox = confidence.score(name, value, evidence, all_lines)
            if retry and value is not None and conf < RETRY_BELOW and bbox and name not in HELPER_FIELDS:
                rr = _retry_field(_best_page(pages, value, evidence), doc_type, name, bbox)
                v2, e2 = typed(name, mask_text(rr.value)), mask_text(rr.evidence)
                c2, b2 = confidence.score(name, v2, e2, all_lines)
                if c2 > conf:
                    value, evidence, conf, bbox = v2, e2, c2, b2
            reads[name] = (value, evidence, conf, bbox)
        _fill_percent(reads)

    fields = {name: FieldRead(value=v, confidence=c, evidence=e, bbox=b)
              for name, (v, e, c, b) in reads.items() if name not in HELPER_FIELDS and v is not None}
    if doc_type in ("income", "community"):
        # What the certificate's QR code says, for the doctor's tampering check.
        qr = read_qr(qr_pages)
        fields["qr_status"] = FieldRead(value=qr.status, confidence=1.0)
        for key, value in qr.values.items():
            fields[f"qr_{key}"] = FieldRead(value=value, confidence=1.0)
    if len(last4s.get("aadhaar", [])) == 1:
        last4 = last4s["aadhaar"][0]
        fields["aadhaar_last4"] = FieldRead(value=last4, confidence=0.9, evidence="XXXX XXXX " + last4)

    seconds = round(time.perf_counter() - t0, 2)
    _log_run(doc_id, doc_type, len(pages), len(fields), seconds)
    return DocResult(doc_id=doc_id, doc_type=doc_type, fields=fields, page_count=len(pages),
                     quality=min((p.quality for p in pages), key=lambda q: q.blur_score),
                     masked_ref=masked_ref, seconds=seconds)


def extract_paths(paths: list[Path], doc_type: DocType | None = None, doc_id: str | None = None,
                  retry: bool | None = None) -> DocResult:
    """Multiple paths are pages of the same document."""
    return extract_pages([img for p in paths for img in preprocess.load_pages(Path(p))], doc_type, doc_id, retry)


def _fill_percent(reads: dict) -> None:
    """Compute marks_percentage from total and max when no percentage is printed."""
    if "marks_percentage" not in reads or reads["marks_percentage"][0] is not None:
        return
    total, max_ = reads.get("marks_total"), reads.get("marks_max")
    if total and max_ and total[0] and max_[0]:
        pct = round(100 * float(total[0]) / float(max_[0]), 2)
        if 0 <= pct <= 100:
            reads["marks_percentage"] = (pct, f"{total[1]} / {max_[1]}", min(total[2], max_[2]), total[3])


def _log_run(doc_id: str, doc_type: str, pages: int, n_fields: int, seconds: float) -> None:
    log_dir = Path(env("LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "extraction.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(UTC).isoformat(), "doc_id": doc_id, "doc_type": doc_type,
                            "pages": pages, "fields": n_fields, "seconds": seconds}) + "\n")
