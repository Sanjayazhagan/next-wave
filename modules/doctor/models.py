"""Doctor findings. The plug-in boundary uses contracts.doctor instead."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Severity = Literal["blocker", "high", "medium", "low"]
POINTS = {"blocker": 100, "high": 30, "medium": 15, "low": 5}


class Finding(BaseModel):
    check: str
    kind: Literal["mismatch", "eligibility", "missing_doc", "file_spec", "quality", "validity"]
    field: str | None
    severity: Severity
    points: int
    detail: str
    values_by_doc: dict[str, str] = {}
    fix: str                 # one action sentence in English


class Diagnosis(BaseModel):
    scheme_id: str | None
    risk_score: int          # 0 to 100, the capped sum of points
    band: Literal["low", "medium", "high", "blocked"]
    findings: list[Finding]
