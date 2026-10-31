"""Receives Telegram updates. Logs ids and types only, never message text."""
import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.channels import TELEGRAM_PREFIX, ChannelError
from app.conversation import ConversationContext, Inbound, handle_inbound
from app.telegram.client import TelegramClient
from app.whatsapp.dedupe import SeenMessages

log = logging.getLogger(__name__)

router = APIRouter()

START_COMMAND = "/start"


def to_inbound(message: dict[str, Any]) -> Inbound:
    if "text" in message:
        return Inbound("text", text=message["text"])
    if "photo" in message:
        largest = message["photo"][-1]  # Sizes are listed smallest first.
        return Inbound("file", media_id=f"{largest['file_id']}|image/jpeg")
    if "document" in message:
        document = message["document"]
        mime_type = document.get("mime_type", "application/octet-stream")
        return Inbound("file", media_id=f"{document['file_id']}|{mime_type}")
    if "voice" in message:
        voice = message["voice"]
        mime_type = voice.get("mime_type", "audio/ogg")
        return Inbound("voice", media_id=f"{voice['file_id']}|{mime_type}")
    return Inbound("other")


async def _handle_message(
    message: dict[str, Any], ctx: ConversationContext, client: TelegramClient
) -> None:
    chat = message["chat"]
    if chat.get("type") != "private":
        return
    try:
        await client.send_typing(str(chat["id"]))
    except ChannelError as exc:
        log.warning("Could not show typing: %s", exc)
    user_id = f"{TELEGRAM_PREFIX}{chat['id']}"
    inbound = to_inbound(message)
    # /start begins again, so a stuck chat can always be restarted.
    if inbound.kind == "text" and inbound.text.strip() == START_COMMAND:
        session = ctx.sessions.active_for_phone(user_id)
        if session and session.status != "running":
            await ctx.manager.cancel(session.id)
    await handle_inbound(user_id, inbound, ctx)


async def _handle_button(
    query: dict[str, Any], ctx: ConversationContext, client: TelegramClient
) -> None:
    try:
        await client.answer_button(query["id"])
    except ChannelError as exc:
        log.warning("Could not answer a button: %s", exc)
    message = query.get("message")
    if message is None or "data" not in query:
        return
    user_id = f"{TELEGRAM_PREFIX}{message['chat']['id']}"
    await handle_inbound(user_id, Inbound("button", button=query["data"]), ctx)


async def process_update(
    update: dict[str, Any],
    ctx: ConversationContext,
    client: TelegramClient,
    seen: SeenMessages,
) -> None:
    update_id = update.get("update_id")
    if not seen.claim(f"{TELEGRAM_PREFIX}{update_id}"):
        log.info("Skipped duplicate update %s", update_id)
        return
    log.info("Received update %s", update_id)
    try:
        if "callback_query" in update:
            await _handle_button(update["callback_query"], ctx, client)
        elif "message" in update:
            await _handle_message(update["message"], ctx, client)
    except Exception:
        log.exception("Failed to handle update %s", update_id)


@router.post("/telegram")
async def receive_update(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, str]:
    state = request.app.state
    secret = state.settings.telegram_webhook_secret
    if state.telegram_client is None or not secret:
        raise HTTPException(status_code=404, detail="Telegram is not set up")
    supplied = x_telegram_bot_api_secret_token or ""
    if not hmac.compare_digest(supplied, secret):
        log.warning("Rejected Telegram update with a bad secret")
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Answer straight away and do the work after, or Telegram resends the update.
    background_tasks.add_task(
        process_update,
        await request.json(),
        state.telegram_context,
        state.telegram_client,
        state.seen,
    )
    return {"status": "ok"}
