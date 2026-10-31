"""What the vision model must return for each document type.

Every field is {value, evidence}; values are strings and are typed in extract.py,
which keeps the JSON schema simple enough for every provider's structured output.
"""
from __future__ import annotations

from pydantic import BaseModel, create_model

from .models import DocType


class Read(BaseModel):
    value: str | None = None
    evidence: str | None = None   # exact printed text the value was read from


FIELDS_BY_TYPE: dict[str, list[str]] = {
    "marksheet": ["full_name", "father_name", "institution", "course", "year_of_study",
                  "marks_percentage", "marks_total", "marks_max", "exam_year"],
    "income": ["full_name", "father_name", "annual_income", "district", "state",
               "certificate_number", "issue_date", "valid_until"],
    "community": ["full_name", "father_name", "caste", "community", "district", "state",
                  "certificate_number", "issue_date", "valid_until"],
}

# Helper fields: read so the model keeps them apart from real fields, never stored themselves.
HELPER_FIELDS = {"marks_total", "marks_max", "caste"}


def schema_for(doc_type: str) -> type[BaseModel]:
    fields = FIELDS_BY_TYPE[doc_type]
    return create_model(f"{doc_type.title().replace('_', '')}Fields",
                        **{f: (Read, Read()) for f in fields})


class DocTypeAnswer(BaseModel):
    doc_type: DocType
