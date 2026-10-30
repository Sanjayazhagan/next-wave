"""Profile schema: extraction -> core -> doctor."""
from pydantic import BaseModel, Field


class ProfileField(BaseModel):
    value: str
    source_document: str  # A document type, or "user_answer" / "user_edit".
    confidence: float = Field(ge=0, le=1)


class Profile(BaseModel):
    fields: dict[str, ProfileField] = {}
