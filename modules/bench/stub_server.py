"""TEST ONLY. A fake of core's session API that replays a short scripted conversation.

It exists so the harness code can be tested without the real agent. Every
response carries "stub": true, bench.py copies that into the CSV, and report.py
refuses those CSVs. Results from this server must never be reported.

    uv run uvicorn modules.bench.stub_server:app --port 8999
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

SCRIPT = [
    ("language", "Choose a language", {"language:en": "English", "language:ta": "தமிழ்"}),
    ("consent", "Do you agree?", {"consent:yes": "I agree", "consent:no": "No thanks"}),
    ("question_state", "Which state do you live in?", None),
    ("documents", "Send your documents", {"documents:done": "Done"}),
    ("scheme", "Pick a scheme", {"scheme:test-a": "Test scheme A", "scheme:test-b": "Test scheme B"}),
    ("approval", "Review ready", {"approval:approve": "Approve", "approval:edit": "Edit"}),
]

app = FastAPI(title="TEST ONLY stub of the session API")
SESSIONS: dict[str, dict] = {}


class Reply(BaseModel):
    text: str | None = None
    button: str | None = None


def _advance(s: dict, answer: str) -> None:
    s["answers"].append(answer)
    kind = SCRIPT[s["step"]][0]
    if kind == "documents" and answer != "documents:done":
        return   # stay on the documents step until Done
    s["step"] += 1


@app.post("/session")
def start() -> dict:
    sid = uuid.uuid4().hex
    SESSIONS[sid] = {"step": 0, "answers": [], "files": 0}
    return {"id": sid, "status": "paused", "stub": True}


@app.get("/session/{sid}")
def view(sid: str) -> dict:
    s = SESSIONS[sid]
    kind, text, buttons = SCRIPT[s["step"]]
    state = next((a for a in s["answers"] if a not in ("language:en", "consent:yes")), None)
    return {"id": sid, "status": "paused", "pending_kind": kind, "prompt": {"kind": kind, "text": text, "buttons": buttons},
            "profile": {"state": {"value": state, "source_document": "user_answer", "confidence": 1.0}} if state else {},
            "filled": {"state": {"label": "State", "source_document": "user_answer", "confidence": 1.0}}
            if kind == "approval" else {},
            "portal_id": "stub-portal", "mode": "explore", "skill_version": None, "outcome": None, "stub": True}


@app.post("/session/{sid}/reply", status_code=202)
def reply(sid: str, body: Reply) -> dict:
    _advance(SESSIONS[sid], body.button or body.text or "")
    return {"status": "accepted", "stub": True}


@app.post("/session/{sid}/files", status_code=202)
async def files(sid: str, file: UploadFile = File(...)) -> dict:
    SESSIONS[sid]["files"] += 1
    return {"status": "accepted", "stub": True}


@app.get("/session/{sid}/audit")
def audit(sid: str) -> list[dict]:
    return [{"type": "step_started", "step": "browser_step", "message": "Filling the form"},
            {"type": "step_started", "step": "self_repair", "message": "Label changed; found it again"}]
