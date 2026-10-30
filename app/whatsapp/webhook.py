import hashlib
import hmac
import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.conversation import ConversationContext
from app.whatsapp.dedupe import SeenMessages
from app.whatsapp.handler import handle_message

# Message text can hold OTPs and phone numbers, so log only ids and types.
log = logging.getLogger(__name__)

router = APIRouter()


def signature_is_valid(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    if not header:
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header)


def iter_messages(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield user messages, skipping delivered and read status updates."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            yield from change.get("value", {}).get("messages", [])


async def process_payload(
    payload: dict[str, Any], ctx: ConversationContext, seen: SeenMessages
) -> None:
    for message in iter_messages(payload):
        message_id = message["id"]
        if not seen.claim(message_id):
            log.info("Skipped duplicate message %s", message_id)
            continue
        log.info("Received %s message %s", message.get("type"), message_id)
        try:
            await handle_message(message, ctx)
        except Exception:
            log.exception("Failed to handle message %s", message_id)


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    request: Request,
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> str:
    verify_token = request.app.state.settings.whatsapp_verify_token
    if mode == "subscribe" and token and hmac.compare_digest(token, verify_token):
        return challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    state = request.app.state
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature_is_valid(raw_body, signature, state.settings.whatsapp_app_secret):
        log.warning("Rejected webhook with a bad signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Answer Meta straight away and do the work after, or Meta retries the delivery.
    background_tasks.add_task(
        process_payload, json.loads(raw_body), state.whatsapp_context, state.seen
    )
    return {"status": "ok"}
