from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Everything a session needs to resume. Stored encrypted in checkpoints."""

    session_id: str
    owner: str  # Phone number, or the session id for web-only sessions.

    # User loop
    consent: dict[str, Any] | None
    file_refs: list[dict[str, str]]
    documents_done: bool
    documents: list[dict[str, Any]]
    profile: dict[str, Any]
    answered: list[str]
    questions_done: bool

    # Scheme
    schemes: list[dict[str, Any]]
    scheme: dict[str, Any] | None
    doctor_report: dict[str, Any] | None
    portal_id: str | None

    # Portal run
    browser_session: str | None
    mode: str  # "explore" or "replay"
    steps: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    step_index: int
    skill_version: int | None
    skill_repaired: bool
    filled: dict[str, dict[str, Any]]
    route: str
    strikes: int
    challenge: dict[str, Any] | None
    challenge_tries: int
    missing_field: str | None
    handover_reason: str | None

    # Review and result
    review: dict[str, Any] | None
    review_choice: str | None
    edit_error: str | None
    receipt_number: str | None
    outcome: str | None
    final: dict[str, Any] | None
