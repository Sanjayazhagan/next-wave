"""Turns inbound WhatsApp messages into the shared inbound form."""
from typing import Any

from app.conversation import ConversationContext, Inbound, handle_inbound


def to_inbound(message: dict[str, Any]) -> Inbound:
    kind = message.get("type")
    if kind == "text":
        return Inbound("text", text=message["text"]["body"])
    if kind == "interactive":
        return Inbound("button", button=message["interactive"]["button_reply"]["id"])
    if kind == "audio":
        return Inbound("voice", media_id=message["audio"]["id"])
    if kind in ("image", "document"):
        return Inbound("file", media_id=message[kind]["id"])
    return Inbound("other")


async def handle_message(message: dict[str, Any], ctx: ConversationContext) -> None:
    await handle_inbound(message["from"], to_inbound(message), ctx)
