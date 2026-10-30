"""Turns an inbound message from any chat app into a graph reply."""
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.channels import ChannelError
from app.config import Settings
from app.language import LanguageError, LanguageService
from app.sessions import Channel, Session, SessionManager, SessionStore
from app.vault import FileStore

log = logging.getLogger(__name__)

ENGLISH = "en"
STOP_WORDS = ("stop", "/stop")
CANCELLED_TEXT = "Stopped. Message me any time to start again."
NOT_EXPECTING_FILE_TEXT = "I'm not expecting a file right now."
WRONG_FILE_TEXT = "Please send a photo or a PDF."
FILE_FAILED_TEXT = "I couldn't get that file. Please send it again."
VOICE_UNAVAILABLE_TEXT = "I can't listen to voice notes yet. Please type your reply."
VOICE_FAILED_TEXT = "I couldn't understand that voice note. Please try again or type it."
UNSUPPORTED_TEXT = "I can't read that kind of message. Please type your reply."
# Exact answers: translating these would corrupt the digits or letters.
NO_TRANSLATE_KINDS = ("otp", "captcha", "edit")


class Downloader(Protocol):
    async def download_media(self, media_id: str, max_bytes: int) -> tuple[bytes, str]: ...


@dataclass
class Inbound:
    kind: str  # "text", "button", "voice", "file" or "other".
    text: str = ""
    button: str = ""
    media_id: str = ""


@dataclass
class ConversationContext:
    settings: Settings
    downloader: Downloader
    channel: Channel
    language: LanguageService
    files: FileStore
    sessions: SessionStore
    manager: SessionManager


async def handle_inbound(user_id: str, inbound: Inbound, ctx: ConversationContext) -> None:
    session = ctx.sessions.active_for_phone(user_id)
    if session is None:
        await ctx.manager.start(user_id, ctx.settings.default_language)
        return

    if inbound.kind == "text" and inbound.text.strip().lower() in STOP_WORDS:
        await ctx.manager.cancel(session.id)
        await ctx.channel.notify(session, CANCELLED_TEXT)
        return

    reply = await _to_reply(inbound, session, ctx)
    if reply is not None:
        await ctx.manager.reply(session.id, reply)


async def _to_reply(
    inbound: Inbound, session: Session, ctx: ConversationContext
) -> dict[str, Any] | None:
    if inbound.kind == "text":
        return {"text": inbound.text}
    if inbound.kind == "button":
        return {"button": inbound.button}
    if inbound.kind == "voice":
        return await _voice_reply(inbound, session, ctx)
    if inbound.kind == "file":
        return await _file_reply(inbound, session, ctx)
    await ctx.channel.notify(session, UNSUPPORTED_TEXT)
    return None


async def _voice_reply(
    inbound: Inbound, session: Session, ctx: ConversationContext
) -> dict[str, Any] | None:
    if not ctx.language.available:
        await ctx.channel.notify(session, VOICE_UNAVAILABLE_TEXT)
        return None
    try:
        data, mime_type = await ctx.downloader.download_media(
            inbound.media_id, ctx.settings.max_upload_bytes
        )
        heard = await ctx.language.speech_to_text(data, mime_type)
    except (ChannelError, LanguageError) as exc:
        log.warning("Voice note failed: %s", type(exc).__name__)
        await ctx.channel.notify(session, VOICE_FAILED_TEXT)
        return None
    ctx.sessions.set_language(session.id, heard.language)
    if session.pending_kind in NO_TRANSLATE_KINDS:
        return {"text": heard.text}
    return {"text": await ctx.language.translate(heard.text, heard.language, ENGLISH)}


async def _file_reply(
    inbound: Inbound, session: Session, ctx: ConversationContext
) -> dict[str, Any] | None:
    if session.pending_kind != "documents":
        await ctx.channel.notify(session, NOT_EXPECTING_FILE_TEXT)
        return None
    try:
        data, mime_type = await ctx.downloader.download_media(
            inbound.media_id, ctx.settings.max_upload_bytes
        )
    except ChannelError as exc:
        log.warning("File download failed: %s", type(exc).__name__)
        await ctx.channel.notify(session, FILE_FAILED_TEXT)
        return None
    if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
        await ctx.channel.notify(session, WRONG_FILE_TEXT)
        return None
    return {"file_ref": ctx.files.put(data, mime_type), "mime_type": mime_type}
