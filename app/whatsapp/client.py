from typing import Any

import httpx

from app.channels import ChannelError
from app.config import Settings

MAX_TEXT_LENGTH = 4000
MAX_BUTTONS = 3
MAX_BUTTON_TITLE_LENGTH = 20


class WhatsAppError(ChannelError):
    """Meta refused a request. The message holds Meta's error, never the token."""


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._http = http
        self._auth = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
        self._phone_number_id = settings.whatsapp_phone_number_id
        self._graph_url = f"https://graph.facebook.com/{settings.graph_api_version}"
        self._phone_url = f"{self._graph_url}/{settings.whatsapp_phone_number_id}"

    async def send_text(self, to: str, body: str) -> None:
        await self._send(to, {"type": "text", "text": {"body": body[:MAX_TEXT_LENGTH]}})

    async def send_buttons(self, to: str, body: str, buttons: dict[str, str]) -> None:
        """Send reply buttons. `buttons` maps each button id to its title."""
        await self._send(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": id_,
                                    "title": title[:MAX_BUTTON_TITLE_LENGTH],
                                },
                            }
                            for id_, title in list(buttons.items())[:MAX_BUTTONS]
                        ]
                    },
                },
            },
        )

    async def send_image(self, to: str, media_id: str, caption: str = "") -> None:
        image: dict[str, str] = {"id": media_id}
        if caption:
            image["caption"] = caption
        await self._send(to, {"type": "image", "image": image})

    async def send_voice(self, to: str, media_id: str) -> None:
        await self._send(to, {"type": "audio", "audio": {"id": media_id, "voice": True}})

    async def upload_media(self, data: bytes, mime_type: str, file_name: str) -> str:
        response = await self._http.post(
            f"{self._phone_url}/media",
            headers=self._auth,
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (file_name, data, mime_type)},
        )
        self._check(response)
        return response.json()["id"]

    async def download_media(self, media_id: str, max_bytes: int) -> tuple[bytes, str]:
        """Fetch inbound media. Its download URL lasts only 5 minutes."""
        info = await self._http.get(
            f"{self._graph_url}/{media_id}",
            headers=self._auth,
            params={"phone_number_id": self._phone_number_id},
        )
        self._check(info)
        details = info.json()
        if details.get("file_size", 0) > max_bytes:
            raise WhatsAppError("Media file is too large")
        media = await self._http.get(
            details["url"], headers=self._auth, follow_redirects=True
        )
        self._check(media)
        return media.content, details.get("mime_type", "application/octet-stream")

    async def _send(self, to: str, message: dict[str, Any]) -> None:
        response = await self._http.post(
            f"{self._phone_url}/messages",
            headers=self._auth,
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                **message,
            },
        )
        self._check(response)

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_error:
            raise WhatsAppError(f"{response.status_code}: {response.text}")
