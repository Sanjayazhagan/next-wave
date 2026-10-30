"""Agent events: core -> web app, chat channels, benchmark."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal[
    "step_started",
    "captcha_needed",
    "otp_needed",
    "approval_needed",
    "done",
    "error",
    # Added to the six agreed types, so the web app can run the same loop.
    "question_needed",
    "handover_needed",
]


class AgentEvent(BaseModel):
    seq: int = 0  # Rises by one per event; send as Last-Event-ID to reconnect.
    session_id: str
    type: EventType
    step: str | None = None
    message: str = ""
    reasoning: str | None = None
    data: dict[str, Any] = {}
    at: datetime
