"""Internal types for extraction. The plug-in boundary uses contracts.documents instead."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# Same names core uses for ExtractedDocument.document_type.
DocType = Literal["marksheet", "income", "community", "other"]


class Quality(BaseModel):
    blur_score: float
    brightness: float
    skew_deg: float
    too_blurry: bool
    too_dark: bool


class FieldRead(BaseModel):
    """One field as read from one document, with the evidence behind its confidence."""

    value: str | int | float | date
    confidence: float = Field(ge=0, le=1)
    evidence: str | None = None       # printed text the value was read from (masked)
    bbox: list[float] | None = None   # x, y, w, h on the cleaned page image

    def as_text(self, field: str = "") -> str:
        """String form used in contracts.profile.ProfileField (date of birth as DD-MM-YYYY, per core)."""
        if isinstance(self.value, date):
            return self.value.strftime("%d-%m-%Y") if field == "date_of_birth" else self.value.isoformat()
        if isinstance(self.value, float) and self.value.is_integer():
            return str(int(self.value))
        return str(self.value)


class DocResult(BaseModel):
    doc_id: str
    doc_type: DocType
    fields: dict[str, FieldRead]
    quality: Quality
    page_count: int = 1
    masked_ref: str | None = None     # cleaned, masked image in $WORK_DIR
    seconds: float = 0.0
