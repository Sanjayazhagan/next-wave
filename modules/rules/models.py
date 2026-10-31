"""Rule files and rich eligibility results. The plug-in boundary uses contracts.eligibility."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

Op = Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "between", "contains_any"]


class Source(BaseModel):
    url: str
    scraped_at: date


class Review(BaseModel):
    reviewed_by: str
    reviewed_at: date


class Rule(BaseModel):
    id: str
    field: str
    op: Op
    value: Any
    clause: str          # verbatim from the source
    source: int = 0      # index into Scheme.sources


class Unmodelled(BaseModel):
    clause: str
    source: int = 0


class Scheme(BaseModel):
    scheme_id: str
    name: str
    portal_id: str
    benefit_inr: int | None = None
    benefit_text: str | None = None
    deadline: date | None = None
    deadline_clause: str | None = None
    required_docs: list[str] = []
    sources: list[Source]
    review: Review | None = None
    rules: list[Rule]
    unmodelled: list[Unmodelled] = []


class Clause(BaseModel):
    text: str
    source_url: str
    scraped_at: date


class RuleResult(BaseModel):
    rule_id: str
    field: str
    status: Literal["pass", "fail", "unknown"]
    expected: str
    actual: str | None
    clause: Clause


class SchemeMatch(BaseModel):
    scheme_id: str
    name: str
    portal_id: str
    status: Literal["eligible", "not_eligible", "needs_info"]
    results: list[RuleResult]
    also_check: list[Clause] = []    # criteria the engine can't test; shown to the user
    benefit_inr: int | None
    benefit_text: str | None
    deadline: date | None
    required_docs: list[str]


class Question(BaseModel):
    field: str
    text_en: str
    choices: list[str] | None = None
