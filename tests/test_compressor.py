import io
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.plugins import load_plugins
from contracts.portal import DocSpec
from modules.compressor import CannotFit, fit_file, prepare
from modules.compressor.spec import PORTALS_DIR, load_portal_spec, spec_for
from tests.remote_helpers import FIXTURES, needs_tesseract


def _photo(w=3000, h=4000, seed=0) -> bytes:
    """A noisy, text-heavy 'phone photo' that compresses badly."""
    rng = np.random.default_rng(seed)
    img = np.clip(rng.normal(225, 18, (h, w, 3)), 0, 255).astype(np.uint8)
    for i in range(40):
        cv2.putText(img, f"Line {i}: Government of Tamil Nadu certificate text {i * 7}", (120, 150 + i * 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.2, (20, 20, 20), 5)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 97])[1].tobytes()


def _kb(b):
    return len(b) / 1024


def test_jpeg_fits_size_and_dimensions():
    data = _photo()
    spec = DocSpec(doc_type="marksheet", accepted_types=["jpg", "pdf"], max_kb=200, max_px=(1600, 1600))
    t0 = time.perf_counter()
    r = prepare(data, spec, check_legibility=False)
    # The page is turned upright first (one Tesseract read, ~1-2 s on real documents); this synthetic
    # photo is pure speckle noise, Tesseract's slowest case. Real scanned PDFs skip that step and
    # took 0.3-1.1 s each (1 Nov 2026).
    assert time.perf_counter() - t0 < 10
    assert r.data[:3] == b"\xff\xd8\xff" and _kb(r.data) <= 200
    w, h = Image.open(io.BytesIO(r.data)).size
    assert w <= 1600 and h <= 1600
    assert r.info.mime == "image/jpeg" and any(a.startswith("resized 3000x4000") for a in r.info.actions)
    assert any("KB to" in a and "quality" in a for a in r.info.actions)


def test_pdf_only_portal_gets_pdf_under_limit():
    spec = DocSpec(doc_type="*", accepted_types=["pdf"], max_kb=300)
    r = prepare(_photo(), spec, check_legibility=False)
    assert r.data[:5] == b"%PDF-" and _kb(r.data) <= 300 and r.info.pages == 1
    assert "converted to PDF" in r.info.actions


def test_multipage_pdf_stays_multipage():
    pages = [Image.open(io.BytesIO(_photo(1200, 1600, s))).convert("RGB") for s in range(3)]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:], quality=98)
    r = prepare(buf.getvalue(), DocSpec(doc_type="*", accepted_types=["pdf"], max_kb=600), check_legibility=False)
    assert r.info.pages == 3 and _kb(r.data) <= 600


def test_tiny_limit_raises_cannot_fit():
    with pytest.raises(CannotFit):
        prepare(_photo(), DocSpec(doc_type="*", accepted_types=["jpg"], max_kb=2), check_legibility=False)


def test_file_already_within_limits_is_untouched():
    small = _photo(900, 1200)
    r = prepare(small, DocSpec(doc_type="*", accepted_types=["jpg"], max_kb=5000), check_legibility=False)
    assert r.data == small and r.info.actions == ["already within portal limits"]


def test_plugin_passes_through_without_a_spec():
    data = _photo(900, 1200)
    assert load_plugins().compressor is fit_file
    assert fit_file(data, "image/jpeg", "portal-without-spec", "marksheet") == data


def test_plugin_uses_mock_portal_spec():
    out = fit_file(_photo(), "image/jpeg", "mock-scholarship", "income")
    assert out[:5] == b"%PDF-" and len(out) <= 1048576


def test_every_portal_spec_is_valid_and_cites_its_source():
    specs = list(PORTALS_DIR.glob("*.json"))
    assert specs
    for path in specs:
        portal = load_portal_spec(path.stem)
        assert portal.portal_id == path.stem
        assert all(d.source_note for d in portal.documents)


def _fixture_docs():
    d = FIXTURES / "docs"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf")) if d.is_dir() else []


def _all_specs():
    return [(path.stem, spec) for path in PORTALS_DIR.glob("*.json") for spec in load_portal_spec(path.stem).documents]


@needs_tesseract
@pytest.mark.skipif(not _fixture_docs(), reason="no fixtures/docs")
@pytest.mark.parametrize("portal_id,spec", _all_specs())
def test_fixtures_fit_every_portal(portal_id, spec):
    for doc in _fixture_docs():
        r = prepare(doc.read_bytes(), spec)
        assert _kb(r.data) <= spec.max_kb, doc.name
        assert r.info.legible, f"{doc.name} not legible after preparing for {portal_id}: {r.info.actions}"


@needs_tesseract
def test_crushed_file_is_not_legible():
    img = np.full((1400, 1000, 3), 255, np.uint8)
    for i in range(20):
        cv2.putText(img, f"Annual income certificate line {i}", (40, 60 + i * 65), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (0, 0, 0), 2)
    data = cv2.imencode(".png", img)[1].tobytes()
    # A tiny pixel limit squashes the page until the words can't be read.
    spec = DocSpec(doc_type="*", accepted_types=["jpg"], max_kb=500, max_px=(180, 250))
    r = prepare(data, spec)
    assert not r.info.legible and r.info.words_after < r.info.words_before
    # The same page at a sensible size stays legible.
    ok = prepare(data, DocSpec(doc_type="*", accepted_types=["jpg"], max_kb=500))
    assert ok.info.legible
