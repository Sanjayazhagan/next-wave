"""Skill library: a saved run of a portal that can be replayed without the LLM."""
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.db import connect
from contracts.browser import Target


class SkillStep(BaseModel):
    """One recorded action. Holds field names, never the values typed."""

    intent: str
    action: Literal["click", "type", "upload", "wait"]
    target: Target | None = None
    field: str | None = None
    document: str | None = None
    wait_ms: int | None = None


@dataclass
class Skill:
    portal_id: str
    version: int
    steps: list[SkillStep]
    runs: int
    repairs: int


class SkillStore:
    def __init__(self, path: Path) -> None:
        self._db = connect(path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS skills (
                portal_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                steps TEXT NOT NULL,
                created_at TEXT NOT NULL,
                runs INTEGER NOT NULL DEFAULT 0,
                repairs INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (portal_id, version)
            )"""
        )
        self._db.commit()

    def save(self, portal_id: str, steps: list[SkillStep], repaired: bool) -> int:
        """Store a new version, carrying the counts over from the last one."""
        previous = self.latest(portal_id)
        version = previous.version + 1 if previous else 1
        self._db.execute(
            "INSERT INTO skills (portal_id, version, steps, created_at, runs, repairs) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                portal_id,
                version,
                json.dumps([step.model_dump() for step in steps]),
                datetime.now(UTC).isoformat(),
                (previous.runs if previous else 0) + 1,
                (previous.repairs if previous else 0) + int(repaired),
            ),
        )
        self._db.commit()
        return version

    def latest(self, portal_id: str) -> Skill | None:
        row = self._db.execute(
            "SELECT version, steps, runs, repairs FROM skills "
            "WHERE portal_id = ? ORDER BY version DESC LIMIT 1",
            (portal_id,),
        ).fetchone()
        if row is None:
            return None
        version, steps, runs, repairs = row
        return Skill(
            portal_id=portal_id,
            version=version,
            steps=[SkillStep.model_validate(step) for step in json.loads(steps)],
            runs=runs,
            repairs=repairs,
        )

    def record_run(self, portal_id: str, version: int) -> None:
        self._db.execute(
            "UPDATE skills SET runs = runs + 1 WHERE portal_id = ? AND version = ?",
            (portal_id, version),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
