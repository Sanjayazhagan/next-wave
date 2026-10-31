"""The plug-in entry point with the LLM and OCR replaced by test doubles (no keys or tesseract)."""
import asyncio
import importlib

import cv2
import numpy as np

from app.plugins import load_plugins
from contracts.documents import DocumentImage, ExtractionResult
from modules.extraction.ocr import OcrWord

pipeline = importlib.import_module("modules.extraction.pipeline")


def _jpeg() -> bytes:
    img = np.full((800, 1000, 3), 255, np.uint8)
    cv2.putText(img, "INCOME CERTIFICATE", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    return cv2.imencode(".jpg", img)[1].tobytes()


def _fake_ocr(monkeypatch):
    lines = [("S. SATYAJIT", (1, 1, 1)), ("Rs. 2,50,000", (1, 1, 2)),
             ("1234", (1, 1, 3)), ("5678", (1, 1, 3)), ("9012", (1, 1, 3))]
    words = [OcrWord(t, 90, (100 + 70 * i, 100 + 40 * k[2], 60, 20), k) for i, (t, k) in enumerate(lines)]
    monkeypatch.setattr(pipeline.ocr, "read_words", lambda im, min_conf=30: list(words))


def test_core_loads_the_plugin():
    assert load_plugins().extraction is not None


def test_extract_returns_contract_types(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    _fake_ocr(monkeypatch)
    prompts = []

    def fake_vision(images, prompt, schema, caller, system=None):
        prompts.append(caller)
        if caller == "extraction.classify":
            return schema(doc_type="income")
        return schema(full_name={"value": "S. SATYAJIT", "evidence": "S. SATYAJIT"},
                      annual_income={"value": "250000", "evidence": "Rs. 2,50,000"},
                      issue_date={"value": "2025-06-01", "evidence": "01/06/2025"},
                      certificate_number={"value": "UID 1234 5678 9012", "evidence": "1234 5678 9012"})

    monkeypatch.setattr(pipeline, "vision_json", fake_vision)
    monkeypatch.setattr(importlib.import_module("modules.extraction.classify"), "vision_json", fake_vision)

    result = asyncio.run(load_plugins().extraction([DocumentImage(file_ref="core-ref-1", mime_type="image/jpeg", data=_jpeg())]))

    assert isinstance(result, ExtractionResult)
    doc = result.documents[0]
    assert doc.document_type == "income" and doc.file_ref == "core-ref-1"
    assert result.profile.fields["annual_income"].value == "250000"
    assert doc.fields["issue_date"].value == "2025-06-01"          # certificate details stay on the document
    assert "issue_date" not in result.profile.fields
    assert result.profile.fields["full_name"].confidence >= 0.95
    assert doc.fields["aadhaar_last4"].value == "9012"
    assert "1234 5678 9012" not in result.model_dump_json()
    # A low-confidence field (the masked certificate number) may get one zoomed retry.
    assert prompts[:2] == ["extraction.classify", "extraction.extract"]
    assert set(prompts[2:]) <= {"extraction.retry"}


def test_unreadable_upload_is_skipped(monkeypatch):
    result = asyncio.run(load_plugins().extraction([DocumentImage(file_ref="x", mime_type="image/jpeg", data=b"junk")]))
    assert result.documents == [] and result.profile.fields == {}


def test_profile_only_holds_core_field_names(tmp_path, monkeypatch):
    """Certificate details stay on the document; the profile uses core's FIELD_NAMES only."""
    from common.fields import PROFILE_FIELDS
    from modules.extraction.merge import to_contract
    from modules.extraction.models import DocResult, FieldRead, Quality
    from datetime import date

    q = Quality(blur_score=100, brightness=150, skew_deg=0, too_blurry=False, too_dark=False)
    doc = DocResult(doc_id="d", doc_type="income", quality=q, fields={
        "full_name": FieldRead(value="Satyajit", confidence=1), "date_of_birth": FieldRead(value=date(2006, 7, 23), confidence=1),
        "certificate_number": FieldRead(value="TN-1", confidence=1), "qr_status": FieldRead(value="decoded", confidence=1)})
    from modules.extraction.merge import merge_profile
    contract = to_contract(doc, "ref")
    profile = merge_profile([contract])
    assert set(profile.fields) <= PROFILE_FIELDS and profile.fields["date_of_birth"].value == "23-07-2006"
    assert "certificate_number" in contract.fields and "qr_status" in contract.fields
