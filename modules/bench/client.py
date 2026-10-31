"""Client for core's session API (README "Session API", app/api.py).

The agent is conversational: start a session, read the paused prompt with
GET /session/{id}, answer with /reply or /files, read /audit afterwards.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx


class AgentClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=30)
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key}
        self.stub = False   # set when the server says it is the test-only stub

    def _call(self, method: str, path: str, **kwargs) -> Any:
        r = self._http.request(method, f"{self._base}{path}", headers=self._headers, **kwargs)
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict) and body.get("stub"):
            self.stub = True
        return body

    def start(self) -> str:
        return self._call("POST", "/session", json={})["id"]

    def view(self, session_id: str) -> dict:
        """{status, pending_kind, prompt, profile, filled, portal_id, mode, skill_version, outcome}"""
        return self._call("GET", f"/session/{session_id}")

    def reply(self, session_id: str, text: str | None = None, button: str | None = None) -> None:
        self._call("POST", f"/session/{session_id}/reply",
                   json={k: v for k, v in {"text": text, "button": button}.items() if v is not None})

    def upload(self, session_id: str, path: Path) -> None:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._call("POST", f"/session/{session_id}/files", files={"file": (path.name, path.read_bytes(), mime)})

    def audit(self, session_id: str) -> list[dict]:
        return self._call("GET", f"/session/{session_id}/audit")
