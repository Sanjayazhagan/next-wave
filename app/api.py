"""Session API and event stream for the web app and benchmark."""
import hmac
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.redact import mask_for_display
from app.sessions import Session, SessionManager


def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    key: Annotated[str | None, Query()] = None,
) -> None:
    """The browser's EventSource cannot set headers, so `key` is accepted too."""
    supplied = x_api_key or key or ""
    if not hmac.compare_digest(supplied, request.app.state.settings.api_token):
        raise HTTPException(status_code=401, detail="Invalid API key")


router = APIRouter(prefix="/session", dependencies=[Depends(require_api_key)])


class StartRequest(BaseModel):
    phone: str | None = None


class ReplyRequest(BaseModel):
    text: str | None = None
    button: str | None = None


class HandoverRequest(BaseModel):
    action: str = "resume"  # "resume" or "abort".
    receipt_number: str | None = None


def _manager(request: Request) -> SessionManager:
    return request.app.state.manager


def _session(request: Request, session_id: str) -> Session:
    session = request.app.state.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


@router.post("")
async def start_session(body: StartRequest, request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    session = await _manager(request).start(body.phone, settings.default_language)
    return {"id": session.id, "status": session.status}


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    session = _session(request, session_id)
    view = await _manager(request).view(session_id)
    values = view["values"]
    fields = (values.get("profile") or {}).get("fields", {})
    return {
        "id": session.id,
        "status": session.status,
        "pending_kind": session.pending_kind,
        "prompt": view["prompt"],
        "profile": {
            name: {**field, "value": mask_for_display(name, field["value"])}
            for name, field in fields.items()
        },
        "filled": values.get("filled", {}),
        "portal_id": values.get("portal_id"),
        "mode": values.get("mode"),
        "skill_version": values.get("skill_version"),
        "outcome": values.get("outcome"),
    }


@router.post("/{session_id}/reply", status_code=202)
async def reply(
    session_id: str,
    body: ReplyRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    _session(request, session_id)
    background_tasks.add_task(
        _manager(request).reply, session_id, body.model_dump(exclude_none=True)
    )
    return {"status": "accepted"}


@router.post("/{session_id}/files", status_code=202)
async def upload_file(
    session_id: str,
    file: UploadFile,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    session = _session(request, session_id)
    state = request.app.state
    if session.pending_kind != "documents":
        raise HTTPException(status_code=409, detail="Not expecting a file")
    data = await file.read(state.settings.max_upload_bytes + 1)
    if len(data) > state.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    mime_type = file.content_type or "application/octet-stream"
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        raise HTTPException(status_code=415, detail="Send a photo or a PDF")
    file_ref = state.files.put(data, mime_type)
    background_tasks.add_task(
        _manager(request).reply,
        session_id,
        {"file_ref": file_ref, "mime_type": mime_type},
    )
    return {"status": "accepted"}


@router.post("/{session_id}/handover", status_code=202)
async def resume_handover(
    session_id: str,
    body: HandoverRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    session = _session(request, session_id)
    if session.pending_kind != "handover":
        raise HTTPException(status_code=409, detail="Session is not waiting for a helper")
    background_tasks.add_task(
        _manager(request).resume_handover, session_id, body.model_dump(exclude_none=True)
    )
    return {"status": "accepted"}


@router.get("/{session_id}/audit")
def audit_trail(session_id: str, request: Request) -> list[dict[str, Any]]:
    _session(request, session_id)
    events = request.app.state.events.history(session_id)
    return [event.model_dump(mode="json") for event in events]


async def _sse(events: Any, session_id: str, after: int) -> AsyncIterator[str]:
    async for event in events.stream(session_id, after):
        data = json.dumps(event.model_dump(mode="json"))
        yield f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"


@router.get("/{session_id}/events")
def event_stream(
    session_id: str,
    request: Request,
    last_event_id: Annotated[int, Header()] = 0,
) -> StreamingResponse:
    _session(request, session_id)
    return StreamingResponse(
        _sse(request.app.state.events, session_id, last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
