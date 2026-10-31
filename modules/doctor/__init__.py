"""M5 application doctor, loaded by core through app/plugins.py.

    check_application(request: DoctorRequest) -> DoctorResponse

Finds what gets applications rejected before the portal sees it: names that
don't match across documents, failed eligibility on what the documents show,
missing documents, conflicting fields, bad issue dates. The risk score is the
capped sum of each finding's points (blocker 100, high 30, medium 15, low 5),
divided by 100 for the contract. It is a transparent checklist, not a trained model.
"""
from __future__ import annotations

from contracts.doctor import DoctorRequest, DoctorResponse, Mismatch

from .diagnose import diagnose
from .models import Diagnosis

__all__ = ["check_application", "diagnose", "Diagnosis"]


def _scheme(scheme_id: str | None):
    if not scheme_id:
        return None
    try:
        from modules.rules import SCHEMES
    except Exception:  # rules not merged or not loadable: skip the scheme checks
        return None
    return next((s for s in SCHEMES if s.scheme_id == scheme_id), None)


def to_contract(d: Diagnosis) -> DoctorResponse:
    return DoctorResponse(mismatches=[Mismatch(field=f.field or f.check, detail=f.fix) for f in d.findings],
                          risk_score=d.risk_score / 100)


def check_application(request: DoctorRequest) -> DoctorResponse:
    """Core's plug-in entry point."""
    return to_contract(diagnose(request.profile, request.documents, _scheme(request.scheme_id)))
