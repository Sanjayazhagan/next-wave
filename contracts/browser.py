"""Snapshot and actions: core <-> browser worker.

POST   /session                 OpenRequest   -> OpenResponse
POST   /session/{id}/login      LoginRequest  -> Snapshot
GET    /session/{id}/snapshot                 -> Snapshot
POST   /session/{id}/action     Action        -> ActionResult
DELETE /session/{id}
POST   /session/{id}/inject     InjectRequest -> ActionResult

Answer 404 for a session that no longer exists; core then reopens it.
"""
from typing import Any, Literal

from pydantic import BaseModel


class Target(BaseModel):
    """Role and accessible name, so skills survive a page being rebuilt."""

    role: str
    name: str


class FileRules(BaseModel):
    """What one upload accepts. Forms differ, and anything left empty is unstated."""

    formats: list[str] = []  # MIME types.
    min_bytes: int | None = None
    max_bytes: int | None = None
    width: int | None = None  # Exact pixels, as photo and signature uploads often ask.
    height: int | None = None


class PageNode(BaseModel):
    ref: str
    role: str
    name: str
    value: str = ""
    file_rules: FileRules | None = None  # On role "file": what this control states.


class Challenge(BaseModel):
    kind: Literal["captcha", "otp"]
    input: Target | None = None  # A CAPTCHA widget may have no text box.
    submit: Target | None = None
    delivery_mode: str | None = None  # "human_assistance_link": the user does it on a link.
    # Crop this to the CAPTCHA alone: it is sent to the user over WhatsApp.
    image_base64: str | None = None


class Snapshot(BaseModel):
    url: str
    title: str = ""
    nodes: list[PageNode] = []
    screenshot_base64: str | None = None
    # True only when Aadhaar and bank numbers are blanked out of the screenshot.
    # Core never sends an unmasked screenshot to WhatsApp.
    screenshot_masked: bool = False
    challenge: Challenge | None = None
    session_expired: bool = False  # True triggers a re-login.
    error: str | None = None
    receipt_number: str | None = None
    # Profile field -> label, for portals that fill the form without typing steps.
    managed_fields: dict[str, str] = {}
    # The visible text, which is where forms tend to state their upload rules.
    page_text: str = ""
    # What the browser itself can carry, whatever a form allows.
    upload_limits: FileRules | None = None
    # Set by a browser that ties the final submit to the exact page approved.
    observation_id: str | None = None

    def find(self, target: Target) -> PageNode | None:
        for node in self.nodes:
            if node.role == target.role and node.name == target.name:
                return node
        return None


class Action(BaseModel):
    type: Literal["click", "type", "upload", "wait"]
    target: Target | None = None
    value: str | None = None
    file_base64: str | None = None
    file_name: str | None = None
    file_mime: str | None = None
    wait_ms: int | None = None


class ActionResult(BaseModel):
    ok: bool
    error: str | None = None


class OpenRequest(BaseModel):
    portal_id: str


class OpenResponse(BaseModel):
    session_id: str


class LoginRequest(BaseModel):
    portal_user_id: str


class InjectRequest(BaseModel):
    """Chaos inject: chaos script <-> browser worker."""

    script: str
    options: dict[str, Any] = {}
