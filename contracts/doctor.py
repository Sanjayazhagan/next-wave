"""Doctor I/O: doctor <-> core."""
from pydantic import BaseModel, Field

from contracts.documents import ExtractedDocument
from contracts.profile import Profile


class DoctorRequest(BaseModel):
    profile: Profile
    documents: list[ExtractedDocument]
    scheme_id: str | None = None
    language: str = "en"  # The chat's language (ISO 639-1); mismatches come back in it.


class Mismatch(BaseModel):
    field: str  # A readable heading, such as "Income certificate", in the request's language.
    detail: str  # Shown to the user. Must not repeat Aadhaar or bank numbers.


class DoctorResponse(BaseModel):
    mismatches: list[Mismatch]
    risk_score: float = Field(ge=0, le=1)
    allowed_to_continue: bool = True
