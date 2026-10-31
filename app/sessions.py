"""Runs the graph for each session, pausing and resuming on user replies."""
import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from langgraph.types import Command

from app.db import connect
from app.events import EventLog
from contracts.events import EventType

log = logging.getLogger(__name__)

RECURSION_LIMIT = 500
ACTIVE = ("running", "paused", "failed")
EVENT_FOR_KIND: dict[str, EventType] = {
    "captcha": "captcha_needed",
    "otp": "otp_needed",
    "approval": "approval_needed",
    "handover": "handover_needed",
}
HIDDEN_FROM_LOG = {
    "approval": "Review ready for approval",
    "chat": "Chat message sent",
}
BUSY_TEXT = "I'm still working on the last step. I'll message you when I need you."
HELPER_TEXT = "A helper is working on your application. I'll message you when it's done."
OLD_BUTTON_TEXT = "That button is from an earlier message. Please use the latest one."
FAILED_TEXT = (
    "Something went wrong on my side. Your progress is saved. "
    "Send any message and I'll try again from where we stopped."
)


@dataclass
class Session:
    id: str
    phone: str | None
    status: str
    pending_kind: str | None
    language: str


class Channel(Protocol):
    async def deliver(self, session: Session, prompt: dict[str, Any]) -> None: ...

    async def finish(self, session: Session, final: dict[str, Any]) -> None: ...

    async def notify(self, session: Session, text: str) -> None: ...


class SessionStore:
    def __init__(self, path: Path) -> None:
        self._db = connect(path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                phone TEXT,
                status TEXT NOT NULL,
                pending_kind TEXT,
                language TEXT NOT NULL,
                submit_claimed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )"""
        )
        self._db.commit()

    def create(self, phone: str | None, language: str) -> Session:
        session = Session(uuid.uuid4().hex, phone, "running", None, language)
        self._db.execute(
            "INSERT INTO sessions (id, phone, status, language, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session.id, phone, "running", language, datetime.now(UTC).isoformat()),
        )
        self._db.commit()
        return session

    def get(self, session_id: str) -> Session | None:
        row = self._db.execute(
            "SELECT id, phone, status, pending_kind, language FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return Session(*row) if row else None

    def active_for_phone(self, phone: str) -> Session | None:
        marks = ",".join("?" for _ in ACTIVE)
        row = self._db.execute(
            "SELECT id, phone, status, pending_kind, language FROM sessions "
            f"WHERE phone = ? AND status IN ({marks}) "
            "ORDER BY created_at DESC LIMIT 1",
            (phone, *ACTIVE),
        ).fetchone()
        return Session(*row) if row else None

    def with_status(self, status: str) -> list[Session]:
        rows = self._db.execute(
            "SELECT id, phone, status, pending_kind, language FROM sessions "
            "WHERE status = ?",
            (status,),
        ).fetchall()
        return [Session(*row) for row in rows]

    def set_status(self, session_id: str, status: str, pending_kind: str | None) -> None:
        self._db.execute(
            "UPDATE sessions SET status = ?, pending_kind = ? WHERE id = ?",
            (status, pending_kind, session_id),
        )
        self._db.commit()

    def set_language(self, session_id: str, language: str) -> None:
        self._db.execute(
            "UPDATE sessions SET language = ? WHERE id = ?", (language, session_id)
        )
        self._db.commit()

    def claim_submit(self, session_id: str) -> bool:
        """Return True once only, so a restart can never submit twice."""
        cursor = self._db.execute(
            "UPDATE sessions SET submit_claimed = 1 "
            "WHERE id = ? AND submit_claimed = 0",
            (session_id,),
        )
        self._db.commit()
        return cursor.rowcount == 1

    def close(self) -> None:
        self._db.close()


class SessionManager:
    def __init__(
        self, graph: Any, store: SessionStore, events: EventLog, channel: Channel
    ) -> None:
        self._graph = graph
        self._store = store
        self._events = events
        self._channel = channel
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    def _config(session_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": session_id},
            "recursion_limit": RECURSION_LIMIT,
        }

    async def start(self, phone: str | None, language: str) -> Session:
        session = self._store.create(phone, language)
        await self._advance(
            session.id, {"session_id": session.id, "owner": phone or session.id}
        )
        return self._store.get(session.id)

    async def reply(self, session_id: str, reply: dict[str, Any]) -> None:
        session = self._store.get(session_id)
        if session is None or session.status not in ACTIVE:
            return
        if session.status == "failed":
            await self._advance(session_id, None)
            return
        if session.status == "running":
            await self._channel.notify(session, BUSY_TEXT)
            return
        if session.pending_kind == "handover":
            await self._channel.notify(session, HELPER_TEXT)
            return
        button = reply.get("button")
        if button and not button.startswith(f"{session.pending_kind}:"):
            await self._channel.notify(session, OLD_BUTTON_TEXT)
            return
        await self._advance(session_id, Command(resume=reply))

    async def resume_handover(self, session_id: str, reply: dict[str, Any]) -> bool:
        """Let a helper continue. Users cannot reach this over WhatsApp."""
        session = self._store.get(session_id)
        if session is None or session.pending_kind != "handover":
            return False
        await self._advance(session_id, Command(resume=reply))
        return True

    async def view(self, session_id: str) -> dict[str, Any]:
        """The paused prompt and saved values, for the web app."""
        state = await self._graph.aget_state(self._config(session_id))
        prompt = state.interrupts[0].value if state.interrupts else None
        return {"prompt": prompt, "values": state.values}

    async def cancel(self, session_id: str) -> None:
        self._store.set_status(session_id, "cancelled", None)
        self._events.emit(session_id, "done", message="Cancelled by the user")

    async def recover(self) -> None:
        """Pick up sessions that were mid-step when the process died."""
        for session in self._store.with_status("running"):
            log.info("Resuming session %s after a restart", session.id)
            await self._advance(session.id, None)

    async def _advance(self, session_id: str, graph_input: Any) -> None:
        async with self._locks[session_id]:
            self._store.set_status(session_id, "running", None)
            config = self._config(session_id)
            try:
                await self._graph.ainvoke(graph_input, config)
                state = await self._graph.aget_state(config)
            except Exception as exc:
                log.exception("Session %s failed", session_id)
                self._store.set_status(session_id, "failed", None)
                self._events.emit(session_id, "error", message=type(exc).__name__)
                await self._channel.notify(self._store.get(session_id), FAILED_TEXT)
                return

            if state.interrupts:
                await self._pause(session_id, state.interrupts[0].value)
            else:
                await self._complete(session_id, state.values)

    async def _pause(self, session_id: str, prompt: dict[str, Any]) -> None:
        kind = prompt["kind"]
        self._store.set_status(session_id, "paused", kind)
        # These can repeat personal details, and this log is not encrypted.
        # The web app reads them from GET /session/{id} instead.
        message = HIDDEN_FROM_LOG.get(kind, prompt["text"])
        self._events.emit(
            session_id,
            EVENT_FOR_KIND.get(kind, "question_needed"),
            step=kind,
            message=message,
            data={"buttons": prompt.get("buttons") or {}},
        )
        await self._channel.deliver(self._store.get(session_id), prompt)

    async def _complete(self, session_id: str, values: dict[str, Any]) -> None:
        final = values.get("final") or {"text": "All done."}
        self._store.set_status(session_id, "done", None)
        self._events.emit(
            session_id,
            "done",
            message=final["text"],
            data={"outcome": values.get("outcome")},
        )
        await self._channel.finish(self._store.get(session_id), final)
