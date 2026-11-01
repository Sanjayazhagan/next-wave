"""Connects the agent to the real-page bridge in browser-product/ (/core-browser).

This is the mode for live pages. The bridge reads the page as it is, leaves login,
OTP and CAPTCHA to the user, and clicks a final submit only with an approval tied to
the exact review page the user saw.
"""
import uuid
from typing import Any

import httpx

from app.browser import BrowserError, BrowserSessionLost
from app.config import Settings
from app.documents import JPEG, PDF, PNG, parse_rules
from contracts.browser import Action, ActionResult, FileRules, PageNode, Snapshot

TIMEOUT_SECONDS = 60
CONSENT_REF = "agent-consent"
BRIDGE_FILE_ROLE = "fileupload"
SERVICE_FORMATS = [PDF, JPEG, PNG]  # All the bridge will attach.


def node_of(element: dict[str, Any]) -> PageNode:
    """Keep the bridge's exact name, because actions must quote it back."""
    is_file = element["role"] == BRIDGE_FILE_ROLE
    words = " ".join(
        (element["name"], element.get("description", ""), element.get("upload_hint", ""))
    )
    return PageNode(
        ref=element["ref"],
        role="file" if is_file else element["role"],
        name=element["name"],
        value=element.get("value", ""),
        file_rules=parse_rules(words, element.get("accept", "")) if is_file else None,
    )


class BridgeBrowserWorker:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = f"{settings.browser_product_url.rstrip('/')}/core-browser"
        self._headers = {"X-Internal-Key": settings.browser_product_key}
        self._portal_urls = settings.portal_url_map()
        self._limits = FileRules(
            formats=SERVICE_FORMATS, max_bytes=settings.browser_upload_max_bytes
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
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
        body = {"url": url, "consent_ref": CONSENT_REF} if url else {"portal_id": portal_id}
        return (await self._json("POST", "/session", json=body))["session_id"]

    def _snapshot(self, data: dict[str, Any]) -> Snapshot:
        return Snapshot.model_validate(
            {
                **data,
                "nodes": [node_of(element) for element in data["nodes"]],
                "upload_limits": self._limits,
            }
        )

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot:
        data = await self._json(
            "POST", f"/session/{session_id}/login", json={"portal_user_id": portal_user_id}
        )
        return self._snapshot(data)

    async def snapshot(self, session_id: str) -> Snapshot:
        return self._snapshot(await self._json("GET", f"/session/{session_id}/snapshot"))

    async def act(self, session_id: str, action: Action) -> ActionResult:
        body = {**action.model_dump(exclude_none=True), "action_id": str(uuid.uuid4())}
        if action.type == "upload" and action.target:
            body["target"]["role"] = BRIDGE_FILE_ROLE
        response = await self._request("POST", f"/session/{session_id}/action", json=body)
        if response.is_error:
            # Refused on purpose: a changed page, or a step that needs the user.
            return ActionResult(ok=False, error=f"Refused with {response.status_code}")
        return ActionResult.model_validate(response.json())

    async def authorize_submit(
        self, session_id: str, approval_ref: str, observation_id: str
    ) -> None:
        await self._json(
            "POST",
            f"/session/{session_id}/authorize-submit",
            json={
                "approved": True,
                "approval_ref": approval_ref,
                "review_observation_id": observation_id,
            },
        )

    async def close(self, session_id: str) -> None:
        await self._request("DELETE", f"/session/{session_id}")
