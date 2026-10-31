"""Run every check and add up a transparent risk score. Not a trained model."""
from __future__ import annotations

from datetime import date

from contracts.documents import ExtractedDocument
from contracts.portal import DocSpec, PreparedFile
from contracts.profile import Profile

from . import checks
from .models import Diagnosis


def band(score: int, has_blocker: bool) -> str:
    if has_blocker:
        return "blocked"
    return "high" if score >= 60 else "medium" if score >= 20 else "low"


def diagnose(profile: Profile, docs: list[ExtractedDocument], scheme=None,
             prepared: dict[str, PreparedFile] | None = None, specs: dict[str, DocSpec] | None = None,
             quality_by_doc: dict[str, dict] | None = None, today: date | None = None) -> Diagnosis:
    """`scheme` is a modules.rules Scheme (or None when the scheme isn't known or reviewed)."""
    findings = checks.name_consistency(docs)
    if scheme is not None:
        findings += checks.eligibility_recheck(profile, scheme)
        findings += checks.required_docs(docs, scheme)
    if prepared and specs:
        findings += checks.file_spec(prepared, specs)
    findings += checks.field_consistency(docs)
    if quality_by_doc:
        findings += checks.image_quality(quality_by_doc)
    findings += checks.authenticity(docs)
    findings += checks.date_validity(docs, today)
    score = min(100, sum(f.points for f in findings))
    return Diagnosis(scheme_id=getattr(scheme, "scheme_id", None), risk_score=score,
                     band=band(score, any(f.severity == "blocker" for f in findings)), findings=findings)
