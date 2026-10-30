"""Telegram Bot API client. The token is part of every URL, so never log URLs."""
from typing import Any

import httpx

from app.channels import ChannelError
from app.config import Settings

MAX_TEXT_LENGTH = 4000
MAX_BUTTON_ID_BYTES = 64


class TelegramError(ChannelError):
    """Telegram refused a request. Holds Telegram's message, never the token."""


class TelegramClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._files = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}"

    async def _call(
        self,
        method: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._http.post(
                f"{self._api}/{method}", json=json, data=data, files=files
            )
        except httpx.HTTPError as exc:
            # httpx errors can repeat the URL, which holds the token.
            raise TelegramError(f"{method} failed: {type(exc).__name__}") from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(f"{method} returned {response.status_code}") from None
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', 'unknown error')}")
        return body["result"]

    async def set_webhook(self, url: str, secret: str) -> None:
        await self._call(
            "setWebhook",
            json={
                "url": url,
                "secret_token": secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._call(
            "sendMessage", json={"chat_id": chat_id, "text": text[:MAX_TEXT_LENGTH]}
        )

    async def send_buttons(self, chat_id: str, text: str, buttons: dict[str, str]) -> None:
        """Send tap buttons. `buttons` maps each button id to its title."""
        await self._call(
            "sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:MAX_TEXT_LENGTH],
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": title, "callback_data": id_}]
                        for id_, title in buttons.items()
                        if len(id_.encode()) <= MAX_BUTTON_ID_BYTES
                    ]
                },
            },
        )

    async def send_photo(self, chat_id: str, data: bytes, mime_type: str) -> None:
        extension = mime_type.rsplit("/", 1)[-1]
        await self._call(
            "sendPhoto",
            data={"chat_id": chat_id},
            files={"photo": (f"image.{extension}", data, mime_type)},
        )

    async def send_voice(self, chat_id: str, data: bytes) -> None:
        await self._call(
            "sendVoice",
            data={"chat_id": chat_id},
            files={"voice": ("receipt.ogg", data, "audio/ogg")},
        )

    async def answer_button(self, callback_id: str) -> None:
        """Stop the spinner Telegram shows on a pressed button."""
        await self._call("answerCallbackQuery", json={"callback_query_id": callback_id})

    async def download_media(self, media_id: str, max_bytes: int) -> tuple[bytes, str]:
        """Fetch inbound media. `media_id` is "file_id|mime_type"."""
        file_id, _, mime_type = media_id.partition("|")
        info = await self._call("getFile", json={"file_id": file_id})
        if info.get("file_size", 0) > max_bytes:
            raise TelegramError("Media file is too large")
        try:
            response = await self._http.get(f"{self._files}/{info['file_path']}")
        except httpx.HTTPError as exc:
            raise TelegramError(f"Download failed: {type(exc).__name__}") from None
        if response.is_error:
            raise TelegramError(f"Download returned {response.status_code}")
        return response.content, mime_type or "application/octet-stream"
