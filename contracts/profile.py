"""Profile schema: extraction -> core -> doctor."""
from pydantic import BaseModel, Field


# Use these names, so every module means the same thing by a field. Add to this list
# on a sync call rather than inventing a new name. Values are in English.
FIELD_NAMES = {
    "full_name": "As printed on the document",
    "date_of_birth": "DD-MM-YYYY",
    "gender": "Male, Female or Other",
    "state": "Full English name, such as Tamil Nadu",
    "district": "Full English name",
    "course": "Such as Class 12 or B.E. second year",
    "marks_percentage": "Digits, such as 87.5",
    "annual_income": "Rupees per year, digits only, such as 120000",
    "community": "BC / MBC, SC / ST or General",
    "father_name": "As printed on the document",
    "mother_name": "As printed on the document",
    "aadhaar_number": "12 digits. Sensitive: never log or send it to an AI",
    "bank_account_number": "Digits. Sensitive: never log or send it to an AI",
    "bank_ifsc": "Such as SBIN0001234",
}


class ProfileField(BaseModel):
    value: str
    source_document: str  # A document type, or "user_answer" / "user_edit".
    confidence: float = Field(ge=0, le=1)


class Profile(BaseModel):
    fields: dict[str, ProfileField] = {}
