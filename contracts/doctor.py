"""Doctor I/O: doctor <-> core."""
from pydantic import BaseModel, Field

from contracts.documents import ExtractedDocument
from contracts.profile import Profile


class DoctorRequest(BaseModel):
    profile: Profile
    documents: list[ExtractedDocument]
    scheme_id: str | None = None


class Mismatch(BaseModel):
    field: str
    detail: str  # Must not repeat Aadhaar or bank numbers.


class DoctorResponse(BaseModel):
    mismatches: list[Mismatch]
    risk_score: float = Field(ge=0, le=1)
