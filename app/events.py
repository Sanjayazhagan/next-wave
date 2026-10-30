"""Agent event stream and audit trail."""
import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import connect
from app.redact import redact
from contracts.events import AgentEvent, EventType


class EventLog:
    def __init__(self, path: Path) -> None:
        self._db = connect(path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                step TEXT,
                message TEXT NOT NULL,
                reasoning TEXT,
                data TEXT NOT NULL,
                at TEXT NOT NULL
            )"""
        )
        self._db.commit()
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def emit(
        self,
        session_id: str,
        type: EventType,
        step: str | None = None,
        message: str = "",
        reasoning: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """Record an event. All text is masked here, the one way into the log."""
        event = AgentEvent(
            session_id=session_id,
            type=type,
            step=step,
            message=redact(message),
            reasoning=redact(reasoning) if reasoning else None,
            data=json.loads(redact(json.dumps(data or {}))),
            at=datetime.now(UTC),
        )
        cursor = self._db.execute(
            "INSERT INTO events (session_id, type, step, message, reasoning, data, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                event.type,
                event.step,
                event.message,
                event.reasoning,
                json.dumps(event.data),
                event.at.isoformat(),
            ),
        )
        self._db.commit()
        event.seq = cursor.lastrowid
        for queue in self._subscribers[session_id]:
            queue.put_nowait(event)
        return event

    def history(self, session_id: str, after: int = 0) -> list[AgentEvent]:
        rows = self._db.execute(
            "SELECT seq, session_id, type, step, message, reasoning, data, at "
            "FROM events WHERE session_id = ? AND seq > ? ORDER BY seq",
            (session_id, after),
        ).fetchall()
        return [
            AgentEvent(
                seq=seq,
                session_id=sid,
                type=type_,
                step=step,
                message=message,
                reasoning=reasoning,
                data=json.loads(data),
                at=at,
            )
            for seq, sid, type_, step, message, reasoning, data, at in rows
        ]

    async def stream(self, session_id: str, after: int = 0) -> AsyncIterator[AgentEvent]:
        """Yield stored events, then live ones until the session is done."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._subscribers[session_id].add(queue)
        try:
            last_seq = after
            for event in self.history(session_id, after):
                last_seq = event.seq
                yield event
                if event.type == "done":
                    return
            while True:
                event = await queue.get()
                if event.seq > last_seq:
                    last_seq = event.seq
                    yield event
                    if event.type == "done":
                        return
        finally:
            self._subscribers[session_id].discard(queue)

    def close(self) -> None:
        self._db.close()
