"""Connects the agent to the general browser API in browser-product/ (its v2 API).

Unlike the fixed portal flow in browser_product.py, this drives any page step by
step, so the planner, saved skills and self-repair all work on it.

The service refuses login, CAPTCHA, OTP and submit controls here until a reviewed
adapter exists for that portal, and it reports them rather than guessing. This raises
those as errors, so the graph hands over to a helper instead of pressing on.
"""
import uuid
from typing import Any

import httpx

from app.browser import BrowserError, BrowserSessionLost
from app.config import Settings
from app.documents import JPEG, PDF, PNG, parse_rules
from contracts.browser import Action, ActionResult, FileRules, PageNode, Snapshot, Target

TIMEOUT_SECONDS = 60
SOURCE_REF = "core-profile"
ROLE_FOR_TYPE = {"checkbox": "checkbox", "radio": "radio", "file": "file"}
ROLE_FOR_TAG = {"select": "combobox", "textarea": "textarea", "a": "link", "button": "button"}
BUTTON_TYPES = ("button", "submit", "reset")
HUMAN_ONLY = "human_auth"  # The service's risk label for login and challenge controls.
SERVICE_FORMATS = [PDF, JPEG, PNG]  # All the service's artifact store will hold.


def role_of(element: dict[str, Any]) -> str:
    if element.get("role"):
        return element["role"]
    kind = element.get("type", "")
    if element.get("tag") == "input":
        if kind in BUTTON_TYPES:
            return "button"
        return ROLE_FOR_TYPE.get(kind, "textbox")
    return ROLE_FOR_TAG.get(element.get("tag", ""), "text")


def name_of(element: dict[str, Any]) -> str:
    return element.get("label") or element.get("name") or element["ref"]


def file_rules_of(element: dict[str, Any]) -> FileRules | None:
    """Read an upload control's rules from what the form says about it."""
    if role_of(element) != "file":
        return None
    words = f"{element.get('label', '')} {element.get('description', '')}"
    return parse_rules(words, element.get("accept", ""))


class GeneralBrowserWorker:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = f"{settings.browser_product_url.rstrip('/')}/integration/v2/browser"
        self._headers = {"X-Internal-Key": settings.browser_product_key}
        self._portal_urls = settings.portal_url_map()
        self._subjects: dict[str, str] = {}
        self._limits = FileRules(
            formats=SERVICE_FORMATS, max_bytes=settings.browser_upload_max_bytes
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", headers=self._headers,
                timeout=TIMEOUT_SECONDS, **kwargs,
            )
        except httpx.HTTPError as exc:
            raise BrowserError(f"Browser service unreachable: {type(exc).__name__}") from None
        if response.status_code == 404:
            raise BrowserSessionLost(path)
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._request(method, path, **kwargs)
        if response.is_error:
            raise BrowserError(f"Browser service answered {response.status_code}")
        return response.json()

    async def open(self, portal_id: str, fields: dict[str, str] | None = None) -> str:
        url = self._portal_urls.get(portal_id)
        if not url:
            raise BrowserError(f"No address set for portal {portal_id}: add it to PORTAL_URLS")
        # An opaque subject, so the service never sees a phone number.
        subject = f"agent-{uuid.uuid4().hex}"
        created = await self._json(
            "POST",
            "/contexts",
            json={
                "request_id": uuid.uuid4().hex,
                "url": url,
                "subject": subject,
                "consent_ref": "agent-consent",
            },
        )
        self._subjects[created["id"]] = subject
        return created["id"]

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot:
        return await self.snapshot(session_id)

    async def _observe(self, session_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/contexts/{session_id}/observe")

    async def snapshot(self, session_id: str) -> Snapshot:
        observation = await self._observe(session_id)
        # One sensitive box must not stop a whole form, so hide it from the planner.
        usable = [e for e in observation["elements"] if e.get("risk") != HUMAN_ONLY]
        if observation.get("waiting_human") and not usable:
            raise BrowserError("This page needs a login or challenge adapter")
        return Snapshot(
            url=observation["url"],
            title=observation.get("title", ""),
            nodes=[
                PageNode(
                    ref=element["ref"],
                    role=role_of(element),
                    name=name_of(element),
                    value=element.get("value", ""),
                    file_rules=file_rules_of(element),
                )
                for element in usable
            ],
            page_text=observation.get("text", ""),
            upload_limits=self._limits,
            screenshot_base64=observation.get("screenshot_base64"),
            screenshot_masked=True,  # The service blanks sensitive controls.
        )

    @staticmethod
    def _find(observation: dict[str, Any], target: Target | None) -> dict[str, Any] | None:
        if target is None:
            return None
        for element in observation["elements"]:
            if role_of(element) == target.role and name_of(element) == target.name:
                return element
        return None

    async def _artifact(self, session_id: str, action: Action, accept: str) -> str:
        name = action.file_name or ""
        accept = accept.lower()
        # The service matches extensions literally, but a form may list only one spelling.
        if name.endswith(".jpg") and ".jpeg" in accept and ".jpg" not in accept:
            name = f"{name[:-4]}.jpeg"
        created = await self._json(
            "POST",
            f"/contexts/{session_id}/artifacts",
            json={
                "subject": self._subject(session_id),
                "source_ref": SOURCE_REF,
                "file_name": name,
                "mime_type": action.file_mime,
                "file_base64": action.file_base64,
            },
        )
        return created["artifact_id"]

    def _subject(self, session_id: str) -> str:
        """The service does not report this, so a restart here means reopening."""
        subject = self._subjects.get(session_id)
        if subject is None:
            raise BrowserSessionLost(session_id)
        return subject

    async def act(self, session_id: str, action: Action) -> ActionResult:
        # Targets are tied to one observation, and a pause for the model can outlast it.
        observation = await self._observe(session_id)
        element = self._find(observation, action.target)
        if action.target is not None and element is None:
            return ActionResult(ok=False, error=f"No element named {action.target.name}")

        body: dict[str, Any] = {
            "action_id": uuid.uuid4().hex,
            "observation_id": observation["observation_id"],
            "target_ref": element["ref"] if element else None,
        }
        if action.type == "click":
            body["kind"] = "click"
        elif action.type == "wait":
            body["kind"] = "wait"
        elif action.type == "type":
            is_select = element and element.get("tag") == "select"
            body.update(
                kind="select" if is_select else "fill",
                value=action.value or "",
                verified=True,
                source_ref=SOURCE_REF,
            )
        elif action.type == "upload":
            artifact_id = await self._artifact(session_id, action, element.get("accept", ""))
            body.update(
                kind="upload", artifact_id=artifact_id, verified=True, source_ref=SOURCE_REF
            )

        response = await self._request("POST", f"/contexts/{session_id}/actions", json=body)
        if response.is_error:
            # Refused on purpose: a stale page, or a control needing a dedicated adapter.
            return ActionResult(ok=False, error=f"Refused with {response.status_code}")
        effect = response.json().get("effect") or {}
        if effect.get("matched") is False:
            return ActionResult(ok=False, error="The page did not keep the value")
        return ActionResult(ok=True)

    async def close(self, session_id: str) -> None:
        self._subjects.pop(session_id, None)
        await self._request("DELETE", f"/contexts/{session_id}")
