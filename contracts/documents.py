"""Extracted document schema: extraction -> core."""
from pydantic import BaseModel

from contracts.profile import Profile, ProfileField


class DocumentImage(BaseModel):
    file_ref: str
    mime_type: str
    data: bytes


class ExtractedDocument(BaseModel):
    document_type: str  # For example "marksheet", "income", "community".
    fields: dict[str, ProfileField]
    file_ref: str


class ExtractionResult(BaseModel):
    profile: Profile
    documents: list[ExtractedDocument]
