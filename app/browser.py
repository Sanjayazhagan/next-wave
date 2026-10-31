"""HTTP client for the browser worker. See contracts/browser.py."""
from typing import Protocol

import httpx

from app.config import Settings
from contracts.browser import (
    Action,
    ActionResult,
    LoginRequest,
    OpenRequest,
    OpenResponse,
    Snapshot,
)

TIMEOUT_SECONDS = 90


class BrowserError(Exception):
    pass


class BrowserSessionLost(BrowserError):
    """The worker no longer has this session, so it must be reopened."""


class BrowserWorker(Protocol):
    async def open(self, portal_id: str, fields: dict[str, str] | None = None) -> str: ...

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot: ...

    async def snapshot(self, session_id: str) -> Snapshot: ...

    async def act(self, session_id: str, action: Action) -> ActionResult: ...

    async def close(self, session_id: str) -> None: ...

    async def authorize_submit(
        self, session_id: str, approval_ref: str, observation_id: str
    ) -> None:
        """Called only when a snapshot carries an observation_id."""
        ...


class HttpBrowserWorker:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._base = settings.browser_worker_url.rstrip("/")

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", timeout=TIMEOUT_SECONDS, **kwargs
            )
        except httpx.HTTPError as exc:
            raise BrowserError(f"Browser worker unreachable: {type(exc).__name__}") from exc
        if response.status_code == 404:
            raise BrowserSessionLost(path)
        if response.is_error:
            raise BrowserError(f"Browser worker answered {response.status_code}")
        return response

    async def open(self, portal_id: str, fields: dict[str, str] | None = None) -> str:
        body = OpenRequest(portal_id=portal_id).model_dump()
        response = await self._request("POST", "/session", json=body)
        return OpenResponse.model_validate(response.json()).session_id

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot:
        body = LoginRequest(portal_user_id=portal_user_id).model_dump()
        response = await self._request("POST", f"/session/{session_id}/login", json=body)
        return Snapshot.model_validate(response.json())

    async def snapshot(self, session_id: str) -> Snapshot:
        response = await self._request("GET", f"/session/{session_id}/snapshot")
        return Snapshot.model_validate(response.json())

    async def act(self, session_id: str, action: Action) -> ActionResult:
        response = await self._request(
            "POST",
            f"/session/{session_id}/action",
            json=action.model_dump(exclude_none=True),
        )
        return ActionResult.model_validate(response.json())

    async def close(self, session_id: str) -> None:
        await self._request("DELETE", f"/session/{session_id}")
