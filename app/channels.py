"""Sends each session's messages through the chat app it started on."""
from typing import Any

from app.sessions import Channel, Session

TELEGRAM_PREFIX = "tg:"


class ChannelError(Exception):
    """A chat app refused a request. Messages must never hold its token."""


class RoutedChannel:
    def __init__(self, whatsapp: Channel, telegram: Channel | None) -> None:
        self._whatsapp = whatsapp
        self._telegram = telegram

    def _pick(self, session: Session) -> Channel:
        if self._telegram and (session.phone or "").startswith(TELEGRAM_PREFIX):
            return self._telegram
        return self._whatsapp

    async def deliver(self, session: Session, prompt: dict[str, Any]) -> None:
        await self._pick(session).deliver(session, prompt)

    async def finish(self, session: Session, final: dict[str, Any]) -> None:
        await self._pick(session).finish(session, final)

    async def notify(self, session: Session, text: str) -> None:
        await self._pick(session).notify(session, text)
