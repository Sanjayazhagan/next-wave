"""Sends the agent's prompts and results over Telegram."""
import logging
from typing import Any

from app.channels import TELEGRAM_PREFIX, ChannelError
from app.conversation import ENGLISH
from app.language import LanguageError, LanguageService, to_voice_note
from app.sessions import Session
from app.telegram.client import TelegramClient
from app.vault import FileStore

log = logging.getLogger(__name__)


def chat_id_of(session: Session) -> str:
    return (session.phone or "").removeprefix(TELEGRAM_PREFIX)


class TelegramChannel:
    def __init__(
        self, client: TelegramClient, language: LanguageService, files: FileStore
    ) -> None:
        self._client = client
        self._language = language
        self._files = files

    async def _localize(self, session: Session, text: str) -> str:
        return await self._language.translate(text, ENGLISH, session.language)

    async def deliver(self, session: Session, prompt: dict[str, Any]) -> None:
        try:
            await self._deliver(session, prompt)
        except ChannelError as exc:
            log.error("Could not send a prompt: %s", exc)

    async def _deliver(self, session: Session, prompt: dict[str, Any]) -> None:
        chat_id = chat_id_of(session)
        if prompt.get("image_ref"):
            data, mime_type = self._files.get(prompt["image_ref"])
            await self._client.send_photo(chat_id, data, mime_type)
        text = await self._localize(session, prompt["text"])
        buttons = prompt.get("buttons")
        if not buttons:
            await self._client.send_text(chat_id, text)
            return
        titles = {
            id_: await self._localize(session, title) for id_, title in buttons.items()
        }
        await self._client.send_buttons(chat_id, text, titles)

    async def finish(self, session: Session, final: dict[str, Any]) -> None:
        try:
            await self._client.send_text(
                chat_id_of(session), await self._localize(session, final["text"])
            )
            if final.get("voice_text"):
                await self._send_voice(session, final["voice_text"])
        except ChannelError as exc:
            log.error("Could not send the result: %s", exc)

    async def _send_voice(self, session: Session, text: str) -> None:
        """A missing voice receipt must not hide the text one already sent."""
        if not self._language.available:
            return
        try:
            spoken = await self._localize(session, text)
            audio = await self._language.text_to_speech(spoken, session.language)
            voice_note = await to_voice_note(audio)
        except LanguageError as exc:
            log.warning("Voice receipt skipped: %s", exc)
            return
        await self._client.send_voice(chat_id_of(session), voice_note)

    async def notify(self, session: Session, text: str) -> None:
        try:
            await self._client.send_text(
                chat_id_of(session), await self._localize(session, text)
            )
        except ChannelError as exc:
            log.error("Could not send a notice: %s", exc)
