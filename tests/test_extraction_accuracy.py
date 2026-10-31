"""Field-level accuracy on real fixtures. Skips when fixtures/ or keys are missing."""
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import pytest

from common.textnorm import norm_text

from tests.remote_helpers import FIXTURES, ROOT, needs_tesseract

DOCS = FIXTURES / "docs"
GT = FIXTURES / "ground_truth"


def _cases():
    if not GT.is_dir():
        return []
    out = []
    for gt in sorted(GT.glob("*.json")):
        src = next((p for p in DOCS.glob(gt.stem + ".*")), None)
        if src:
            out.append((src, gt))
    return out


@needs_tesseract
@pytest.mark.live
@pytest.mark.skipif(not _cases(), reason="no fixtures with ground truth")
@pytest.mark.skipif(not os.getenv("VISION_MODEL") and os.getenv("LLM_BASE_URL"), reason="VISION_MODEL or LLM_BASE_URL not set")
def test_accuracy():
    from modules.extraction.pipeline import extract_paths

    per_type = defaultdict(lambda: [0, 0])
    per_field = defaultdict(lambda: [0, 0])
    for src, gt_path in _cases():
        gt = json.loads(gt_path.read_text())
        doc = extract_paths([src], doc_type=gt["doc_type"], doc_id=src.stem)
        dumped = doc.model_dump_json()
        assert not re.search(r"(?<!\d)\d{12}(?!\d)|\d{4} \d{4} \d{4}", dumped), f"unmasked number in {src.name}"
        for field, want in gt["fields"].items():
            got = doc.fields.get(field)
            ok = got is not None and norm_text(str(got.value)) == norm_text(str(want))
            per_type[gt["doc_type"]][0] += ok
            per_type[gt["doc_type"]][1] += 1
            per_field[field][0] += ok
            per_field[field][1] += 1
    correct = sum(c for c, _ in per_type.values())
    total = sum(t for _, t in per_type.values())
    report = {
        "overall": round(correct / total, 3), "fields_scored": total,
        "per_type": {k: round(c / t, 3) for k, (c, t) in per_type.items()},
        "per_field": {k: round(c / t, 3) for k, (c, t) in per_field.items()},
    }
    out = ROOT / "reports" / "extraction_accuracy.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
