"""Answer the agent's prompts from a benchmark profile, the way a citizen would.

Prompts needing a real person (OTP, CAPTCHA, handover, fixes) return None: the
harness prints them and waits for a human to answer through the normal channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from common.textnorm import norm_text

HUMAN_KINDS = {"otp", "captcha", "handover", "fix", "edit"}


class BenchProfile(BaseModel):
    """fixtures/profiles/<name>.bench.json (git-ignored: it describes a real person)."""

    language: str = "en"
    answers: dict[str, str]                 # question field -> answer, e.g. {"state": "Tamil Nadu"}
    documents: list[str] = []               # paths of real document files to upload
    scheme_id: str | None = None            # pick this scheme if offered, else the first
    portal_user_id: str | None = None       # if missing, a human types it
    expected: dict[str, str] = {}           # filled field -> value the review page must show


@dataclass
class Answer:
    text: str | None = None
    button: str | None = None
    upload: Path | None = None


@dataclass
class Policy:
    profile: BenchProfile
    uploaded: list[str] = field(default_factory=list)

    def _button(self, prompt: dict, *wanted: str) -> str | None:
        buttons = prompt.get("buttons") or {}
        for want in wanted:
            for bid, title in buttons.items():
                if norm_text(bid.split(":", 1)[-1]) == norm_text(want) or norm_text(title) == norm_text(want):
                    return bid
        return None

    def answer(self, kind: str, prompt: dict) -> Answer | None:
        p = self.profile
        if kind in HUMAN_KINDS or kind.startswith("field_"):
            return None
        if kind == "language":
            return Answer(button=self._button(prompt, p.language)) if self._button(prompt, p.language) else Answer(text=p.language)
        if kind in ("consent", "confirm"):
            return Answer(button=self._button(prompt, "yes"))
        if kind.startswith("question_"):
            value = p.answers.get(kind.removeprefix("question_"))
            if value is None:
                return None
            return Answer(button=self._button(prompt, value)) if self._button(prompt, value) else Answer(text=value)
        if kind == "chat":
            return Answer(text=". ".join(f"My {k.replace('_', ' ')} is {v}" for k, v in p.answers.items()) + ".")
        if kind == "documents":
            pending = [d for d in p.documents if d not in self.uploaded]
            if pending:
                self.uploaded.append(pending[0])
                return Answer(upload=Path(pending[0]))
            return Answer(button=self._button(prompt, "done") or "documents:done")
        if kind == "scheme":
            buttons = list((prompt.get("buttons") or {}))
            pick = self._button(prompt, p.scheme_id) if p.scheme_id else None
            return Answer(button=pick or (buttons[0] if buttons else None))
        if kind == "portal_id":
            return Answer(text=p.portal_user_id) if p.portal_user_id else None
        return None
