"""Sends the agent's prompts and results over WhatsApp."""
import logging
from typing import Any

import httpx

from app.language import LanguageError, LanguageService, to_voice_note
from app.sessions import Session
from app.vault import FileStore
from app.whatsapp.client import WhatsAppClient, WhatsAppError

log = logging.getLogger(__name__)

MAX_BUTTON_BODY_LENGTH = 1000
CHOOSE_TEXT = "Please choose:"
ENGLISH = "en"


class WhatsAppChannel:
    def __init__(
        self, client: WhatsAppClient, language: LanguageService, files: FileStore
    ) -> None:
        self._client = client
        self._language = language
        self._files = files

    async def _localize(self, session: Session, text: str) -> str:
        return await self._language.translate(text, ENGLISH, session.language)

    async def deliver(self, session: Session, prompt: dict[str, Any]) -> None:
        if not session.phone:
            return
        try:
            await self._deliver(session, prompt)
        except (WhatsAppError, httpx.HTTPError) as exc:
            log.error("Could not send a prompt: %s", exc)

    async def _deliver(self, session: Session, prompt: dict[str, Any]) -> None:
        if prompt.get("image_ref"):
            await self._send_image(session.phone, prompt["image_ref"])
        text = await self._localize(session, prompt["text"])
        buttons = prompt.get("buttons")
        if not buttons:
            await self._client.send_text(session.phone, text)
            return
        if len(text) > MAX_BUTTON_BODY_LENGTH:
            await self._client.send_text(session.phone, text)
            text = await self._localize(session, CHOOSE_TEXT)
        titles = {
            id_: await self._localize(session, title) for id_, title in buttons.items()
        }
        await self._client.send_buttons(session.phone, text, titles)

    async def _send_image(self, phone: str, image_ref: str) -> None:
        data, mime_type = self._files.get(image_ref)
        extension = mime_type.rsplit("/", 1)[-1]
        media_id = await self._client.upload_media(data, mime_type, f"image.{extension}")
        await self._client.send_image(phone, media_id)

    async def finish(self, session: Session, final: dict[str, Any]) -> None:
        if not session.phone:
            return
        try:
            await self._client.send_text(
                session.phone, await self._localize(session, final["text"])
            )
            if final.get("voice_text"):
                await self._send_voice(session, final["voice_text"])
        except (WhatsAppError, httpx.HTTPError) as exc:
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
        media_id = await self._client.upload_media(voice_note, "audio/ogg", "receipt.ogg")
        await self._client.send_voice(session.phone, media_id)

    async def notify(self, session: Session, text: str) -> None:
        if not session.phone:
            return
        try:
            await self._client.send_text(session.phone, await self._localize(session, text))
        except (WhatsAppError, httpx.HTTPError) as exc:
            log.error("Could not send a notice: %s", exc)
