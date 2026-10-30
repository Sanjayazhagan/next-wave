"""Turns inbound WhatsApp messages into graph replies."""
import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.language import LanguageError, LanguageService
from app.sessions import Session, SessionManager, SessionStore
from app.vault import FileStore
from app.whatsapp.channel import ENGLISH, WhatsAppChannel
from app.whatsapp.client import WhatsAppClient, WhatsAppError

log = logging.getLogger(__name__)

CANCELLED_TEXT = "Stopped. Message me any time to start again."
NOT_EXPECTING_FILE_TEXT = "I'm not expecting a file right now."
WRONG_FILE_TEXT = "Please send a photo or a PDF."
FILE_FAILED_TEXT = "I couldn't get that file. Please send it again."
VOICE_UNAVAILABLE_TEXT = "I can't listen to voice notes yet. Please type your reply."
VOICE_FAILED_TEXT = "I couldn't understand that voice note. Please try again or type it."
UNSUPPORTED_TEXT = "I can't read that kind of message. Please type your reply."
# Exact answers: translating these would corrupt the digits or letters.
NO_TRANSLATE_KINDS = ("otp", "captcha", "edit")


@dataclass
class WhatsAppContext:
    settings: Settings
    client: WhatsAppClient
    channel: WhatsAppChannel
    language: LanguageService
    files: FileStore
    sessions: SessionStore
    manager: SessionManager


async def handle_message(message: dict[str, Any], ctx: WhatsAppContext) -> None:
    phone = message["from"]
    session = ctx.sessions.active_for_phone(phone)
    if session is None:
        await ctx.manager.start(phone, ctx.settings.default_language)
        return

    kind = message.get("type")
    if kind == "text" and message["text"]["body"].strip().lower() == "stop":
        await ctx.manager.cancel(session.id)
        await ctx.channel.notify(session, CANCELLED_TEXT)
        return

    reply = await _to_reply(kind, message, session, ctx)
    if reply is not None:
        await ctx.manager.reply(session.id, reply)


async def _to_reply(
    kind: str | None, message: dict[str, Any], session: Session, ctx: WhatsAppContext
) -> dict[str, Any] | None:
    if kind == "text":
        return {"text": message["text"]["body"]}
    if kind == "interactive":
        return {"button": message["interactive"]["button_reply"]["id"]}
    if kind == "audio":
        return await _voice_reply(message["audio"], session, ctx)
    if kind in ("image", "document"):
        return await _file_reply(message[kind], session, ctx)
    await ctx.channel.notify(session, UNSUPPORTED_TEXT)
    return None


async def _voice_reply(
    audio: dict[str, Any], session: Session, ctx: WhatsAppContext
) -> dict[str, Any] | None:
    if not ctx.language.available:
        await ctx.channel.notify(session, VOICE_UNAVAILABLE_TEXT)
        return None
    try:
        data, mime_type = await ctx.client.download_media(
            audio["id"], ctx.settings.max_upload_bytes
        )
        heard = await ctx.language.speech_to_text(data, mime_type)
    except (WhatsAppError, LanguageError) as exc:
        log.warning("Voice note failed: %s", type(exc).__name__)
        await ctx.channel.notify(session, VOICE_FAILED_TEXT)
        return None
    ctx.sessions.set_language(session.id, heard.language)
    if session.pending_kind in NO_TRANSLATE_KINDS:
        return {"text": heard.text}
    return {"text": await ctx.language.translate(heard.text, heard.language, ENGLISH)}


async def _file_reply(
    media: dict[str, Any], session: Session, ctx: WhatsAppContext
) -> dict[str, Any] | None:
    if session.pending_kind != "documents":
        await ctx.channel.notify(session, NOT_EXPECTING_FILE_TEXT)
        return None
    try:
        data, mime_type = await ctx.client.download_media(
            media["id"], ctx.settings.max_upload_bytes
        )
    except WhatsAppError as exc:
        log.warning("File download failed: %s", type(exc).__name__)
        await ctx.channel.notify(session, FILE_FAILED_TEXT)
        return None
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        await ctx.channel.notify(session, WRONG_FILE_TEXT)
        return None
    return {"file_ref": ctx.files.put(data, mime_type), "mime_type": mime_type}
