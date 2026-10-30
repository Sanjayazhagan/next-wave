"""Versioned core/browser integration inputs, independent of the demo console."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class VerifiedField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    verified: bool

class BrowserStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=8, max_length=100)
    subject: str = Field(min_length=1, max_length=100)
    consent_ref: str = Field(min_length=1, max_length=200)
    portal: Literal['mock-scholarship'] = 'mock-scholarship'
    mode: Literal['demo'] = 'demo'
    fields: dict[str, VerifiedField]

class BrowserCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action_id: str = Field(min_length=8, max_length=100)
    expected_state: str
    kind: Literal['otp','human','fill','approve','edit','resume','reconcile','poll','inject','action']
    payload: dict = Field(default_factory=dict)

class PreparedDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=200)
    file_name: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,100}\.pdf$')
    file_base64: str = Field(min_length=8, max_length=1400000)
