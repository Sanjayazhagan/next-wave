"""Connects the agent to the browser service in browser-product/.

That service's v1 API runs a whole portal as one state machine, so this presents it
to the agent as small pages: answer the challenges, fill the application, then final
submit. The planner, approval step and final-submit guard all work unchanged.

It supports only the service's fictional scholarship portal so far.
"""
import logging
import uuid
from typing import Any

import httpx

from app.browser import BrowserError, BrowserSessionLost
from app.config import Settings
from contracts.browser import (
    Action,
    ActionResult,
    Challenge,
    FileRules,
    PageNode,
    Snapshot,
    Target,
)

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60
SOURCE_REF = "core-profile"
OTP_INPUT = Target(role="textbox", name="OTP")
OTP_SUBMIT = Target(role="button", name="Verify")
CAPTCHA_INPUT = Target(role="textbox", name="Challenge answer")
CAPTCHA_SUBMIT = Target(role="button", name="Check")
UPLOAD_CONTROL = PageNode(ref="upload", role="file", name="Upload document")
FILL_BUTTON = PageNode(ref="fill", role="button", name="Fill application")
FINAL_SUBMIT = PageNode(ref="final", role="button", name="Final submit")
# The service's field name -> (the profile's field name, label shown on review).
FIELDS = {
    "student_name": ("full_name", "Student name"),
    "course": ("course", "Course"),
    "income": ("annual_income", "Annual income"),
    "state": ("state", "State"),
    "category": ("community", "Community"),
}


def _fields_for_service(fields: dict[str, str]) -> dict[str, dict[str, Any]]:
    missing = [ours for ours, _ in FIELDS.values() if not fields.get(ours)]
    if missing:
        raise BrowserError(f"Profile is missing {', '.join(missing)}")
    result = {}
    for theirs, (ours, _) in FIELDS.items():
        value = fields[ours]
        if theirs == "category":
            value = value.split("/")[0].strip()  # "BC / MBC" becomes "BC".
        result[theirs] = {
            "value": value, "source_ref": SOURCE_REF, "confidence": 1.0, "verified": True,
        }
    return result


class BrowserProductWorker:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = settings.browser_product_url.rstrip("/")
        self._headers = {"X-Internal-Key": settings.browser_product_key}
        self._typed: dict[str, str] = {}  # Held only until the matching click.
        self._tasks: dict[str, dict[str, str]] = {}  # Open CAPTCHA tasks.
        self._review_hashes: dict[str, str] = {}
        self._subjects: dict[str, str] = {}
        self._documents: dict[str, dict[str, str]] = {}  # Held until the fill.
        self._upload_rules: dict[str, FileRules] = {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", headers=headers,
                timeout=TIMEOUT_SECONDS, **kwargs,
            )
        except httpx.HTTPError as exc:
            raise BrowserError(f"Browser service unreachable: {type(exc).__name__}") from None
        if response.status_code == 404:
            raise BrowserSessionLost(path)
        if response.is_error:
            raise BrowserError(f"Browser service answered {response.status_code}")
        return response.json()

    async def _command(
        self, session_id: str, state: str, kind: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/integration/v1/sessions/{session_id}/commands",
            json={
                "action_id": uuid.uuid4().hex,
                "expected_state": state,
                "kind": kind,
                "payload": payload or {},
            },
        )

    async def open(self, portal_id: str, fields: dict[str, str] | None = None) -> str:
        # An opaque subject, so the service never sees a phone number.
        subject = f"agent-{uuid.uuid4().hex}"
        started = await self._request(
            "POST",
            "/integration/v1/sessions",
            json={
                "request_id": uuid.uuid4().hex,
                "subject": subject,
                "consent_ref": "agent-consent",
                "mode": "demo",
                "fields": _fields_for_service(fields or {}),
            },
        )
        self._subjects[started["id"]] = subject
        self._upload_rules[started["id"]] = await self._portal_rules()
        return started["id"]

    async def _portal_rules(self) -> FileRules:
        """The service's catalog states what its upload accepts. These sessions take no
        portal ID, because they always run the one entry with an application flow."""
        catalog = await self._request("GET", "/integration/v1/portals")
        portal = next((p for p in catalog["portals"] if p.get("application_flow")), {})
        upload = portal.get("upload") or {}
        mime = upload.get("mime")
        return FileRules(formats=[mime] if mime else [], max_bytes=upload.get("max_bytes"))

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot:
        return await self.snapshot(session_id)  # The session starts at the OTP step.

    async def _captcha_image(self, session_id: str) -> str:
        """Claim the service's human task to get a crop of just the challenge."""
        created = await self._request(
            "POST", "/integration/v1/human-tasks", json={"session_id": session_id}
        )
        task_id = created["task_id"]
        invitation = created["assistance_path"].split("#", 1)[1]
        claimed = await self._request(
            "POST", f"/assist-api/{task_id}/claim", json={"invitation": invitation}
        )
        self._tasks[session_id] = {"id": task_id, "bearer": claimed["bearer"]}
        view = await self._request(
            "GET",
            f"/assist-api/{task_id}/view",
            headers={"Authorization": f"Bearer {claimed['bearer']}"},
        )
        return view["screenshot_base64"]

    async def snapshot(self, session_id: str) -> Snapshot:
        session = await self._request("GET", f"/integration/v1/sessions/{session_id}")
        state = session["state"]
        url = f"{self._base}/mock/{state}"
        if state == "otp_needed":
            challenge = Challenge(kind="otp", input=OTP_INPUT, submit=OTP_SUBMIT)
            return Snapshot(url=url, title="Login", challenge=challenge)
        if state == "captcha_needed":
            challenge = Challenge(
                kind="captcha",
                input=CAPTCHA_INPUT,
                submit=CAPTCHA_SUBMIT,
                image_base64=await self._captcha_image(session_id),
            )
            return Snapshot(url=url, title="Security check", challenge=challenge)
        if state == "form_ready":
            # The fill button appears only once a document is attached, so a form can
            # never be filled without one.
            if session_id in self._documents:
                return Snapshot(url=url, title="Application form", nodes=[FILL_BUTTON])
            rules = self._upload_rules.get(session_id)
            control = UPLOAD_CONTROL.model_copy(update={"file_rules": rules})
            return Snapshot(url=url, title="Application form", nodes=[control])
        if state == "approval_needed":
            self._review_hashes[session_id] = session["review_hash"]
            return Snapshot(
                url=url,
                title="Review",
                nodes=[FINAL_SUBMIT],
                managed_fields={ours: label for ours, label in FIELDS.values()},
            )
        if state == "submitted":
            return Snapshot(url=url, title="Done", receipt_number=session["receipt_id"])
        return Snapshot(url=url, title=state, error=f"Unexpected portal state: {state}")

    async def _answer_captcha(self, session_id: str, answer: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is None:
            raise BrowserError("No CAPTCHA task is open")
        await self._request(
            "POST",
            f"/assist-api/{task['id']}/answer",
            json={"answer": answer},
            headers={"Authorization": f"Bearer {task['bearer']}"},
        )

    def _attach(self, session_id: str, action: Action) -> ActionResult:
        """Hold the document. It travels to the browser with the fill command."""
        if not action.file_base64 or session_id not in self._subjects:
            return ActionResult(ok=False, error="No document to attach")
        self._documents[session_id] = {
            "subject": self._subjects[session_id],
            "source_ref": SOURCE_REF,
            "file_name": action.file_name or "",
            "file_base64": action.file_base64,
        }
        return ActionResult(ok=True)

    async def act(self, session_id: str, action: Action) -> ActionResult:
        name = action.target.name if action.target else ""
        if action.type == "wait":
            return ActionResult(ok=True)
        if action.type == "type":
            self._typed[session_id] = action.value or ""
            return ActionResult(ok=True)
        if action.type == "upload":
            return self._attach(session_id, action)
        if action.type != "click":
            return ActionResult(ok=False, error=f"{action.type} is not supported here")

        # A wrong answer is not an error here: the next snapshot shows the challenge
        # again, and the graph counts the tries.
        if name == OTP_SUBMIT.name:
            otp = self._typed.pop(session_id, "")
            await self._command(session_id, "otp_needed", "otp", {"otp": otp})
        elif name == CAPTCHA_SUBMIT.name:
            await self._answer_captcha(session_id, self._typed.pop(session_id, ""))
        elif name == FILL_BUTTON.name:
            document = self._documents.get(session_id)
            if document is None:
                return ActionResult(ok=False, error="Attach a document first")
            await self._command(session_id, "form_ready", "fill", document)
        elif name == FINAL_SUBMIT.name:
            review_hash = self._review_hashes.get(session_id)
            if not review_hash:
                return ActionResult(ok=False, error="No review to approve")
            await self._command(
                session_id, "approval_needed", "approve",
                {"confirmed": True, "review_hash": review_hash},
            )
        else:
            return ActionResult(ok=False, error=f"No element named {name}")
        return ActionResult(ok=True)

    async def close(self, session_id: str) -> None:
        """The service ends its own sessions, so only local state goes."""
        for held in (
            self._typed, self._tasks, self._review_hashes, self._subjects, self._documents,
            self._upload_rules,
        ):
            held.pop(session_id, None)
