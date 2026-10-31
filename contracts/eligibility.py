"""Eligibility I/O: rule engine <-> core."""
from pydantic import BaseModel

from contracts.profile import Profile


class EligibilityRequest(BaseModel):
    profile: Profile


class SchemeMatch(BaseModel):
    scheme_id: str
    name: str
    portal_id: str
    rank: int  # 1 is the best match.
    cited_clause: str


class SchemeQuestion(BaseModel):
    """A detail that decides a scheme, which core asks before offering any."""

    field: str
    text: str
    choices: dict[str, str] = {}  # Value to store -> button label. Empty means typed.


class EligibilityResponse(BaseModel):
    schemes: list[SchemeMatch]
    questions: list[SchemeQuestion] = []
