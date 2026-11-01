"""What the vision model must return for each document type.

Every field is {value, evidence}. Values are typed in pipeline.py, so the reply is
accepted however the model writes a value (string, number, or a bare value without
the {value, evidence} wrapper): a rejected reply means sending the images again.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, create_model, field_validator, model_validator


class Read(BaseModel):
    value: str | None = None
    evidence: str | None = None   # exact printed text the value was read from

    @model_validator(mode="before")
    @classmethod
    def _bare_value(cls, data: Any) -> Any:
        return {"value": data} if isinstance(data, (str, int, float)) else data

    @field_validator("value", "evidence", mode="before")
    @classmethod
    def _as_text(cls, v: Any) -> Any:
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


FIELDS_BY_TYPE: dict[str, list[str]] = {
    "marksheet": ["full_name", "father_name", "institution", "course", "year_of_study",
                  "marks_percentage", "marks_total", "marks_max", "exam_year"],
    "income": ["full_name", "father_name", "annual_income", "district", "state",
               "certificate_number", "issue_date", "valid_until"],
    "community": ["full_name", "father_name", "caste", "community", "district", "state",
                  "certificate_number", "issue_date", "valid_until"],
}
ALL_FIELDS = list(dict.fromkeys(f for fields in FIELDS_BY_TYPE.values() for f in fields))

# Helper fields: read so the model keeps them apart from real fields, never stored themselves.
HELPER_FIELDS = {"marks_total", "marks_max", "caste"}


def schema_for(doc_type: str | None) -> type[BaseModel]:
    """One document type's fields, or (doc_type None) every field plus doc_type, for a single call."""
    fields = FIELDS_BY_TYPE[doc_type] if doc_type else ALL_FIELDS
    extra = {} if doc_type else {"doc_type": (str, "other")}
    return create_model(f"{(doc_type or 'any').title()}Fields", **extra,
                        **{f: (Read | None, None) for f in fields})


def shape(doc_type: str | None) -> str:
    """A short reply format, instead of the full JSON Schema (fewer tokens, same result)."""
    fields = FIELDS_BY_TYPE[doc_type] if doc_type else ALL_FIELDS
    head = '"doc_type": "marksheet" | "income" | "community" | "other", ' if not doc_type else ""
    return ("Reply with one JSON object only: {" + head + '"<field>": {"value": string or null, '
            '"evidence": string or null}, ...} with these fields: ' + ", ".join(fields) + ".")


def doc_type_of(raw: str | None) -> str:
    """Map the model's doc_type (which may be worded loosely) to marksheet/income/community/other."""
    t = (raw or "").lower()
    if "income" in t:
        return "income"
    if any(w in t for w in ("community", "caste", "backward", "obc", "scheduled")):
        return "community"
    if any(w in t for w in ("mark", "grade", "result", "transcript")):
        return "marksheet"
    return "other"
