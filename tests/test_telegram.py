"""Whole conversations, sent through the real Telegram webhook."""
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.plugins import Plugins
from app.standins import StubBrowser
from tests.conftest import API_TOKEN, LANGUAGE_URL, Network

BOT_TOKEN = "12345:bot-token-value"
SECRET = "telegram-webhook-secret"
CHAT_ID = 777001
USER_ID = f"tg:{CHAT_ID}"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


class TelegramChat:
    """One private chat talking to the webhook."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.update_id = 1000

    def send(self, update: dict[str, Any], headers: dict[str, str] = HEADERS):
        self.update_id += 1
        return self.client.post(
            "/telegram", json={"update_id": self.update_id, **update}, headers=headers
        )

    def message(self, **content: Any):
        chat = {"id": CHAT_ID, "type": "private"}
        return self.send({"message": {"message_id": 1, "chat": chat, **content}})

    def text(self, body: str):
        return self.message(text=body)

    def press(self, button_id: str):
        chat = {"id": CHAT_ID, "type": "private"}
        query = {"id": "cb1", "data": button_id, "message": {"chat": chat}}
        return self.send({"callback_query": query})

    def photo(self):
        sizes = [{"file_id": "small"}, {"file_id": "large"}]
        return self.message(photo=sizes)

    def up_to_review(self) -> None:
        self.text("/start")
        self.press("consent:yes")
        self.photo()
        self.press("documents:done")
        self.text("Tamil Nadu")
        self.text("Class 12")
        self.text("120000")
        self.press("question_community:bc")
        self.text("portal-user")
        self.text("123456")
        self.text("ABCD")


@pytest.fixture
def telegram_client(make_client) -> TestClient:
    return make_client(telegram_bot_token=BOT_TOKEN, telegram_webhook_secret=SECRET)


@pytest.fixture
def chat(telegram_client: TestClient) -> TelegramChat:
    return TelegramChat(telegram_client)


def test_start_asks_for_consent_with_tap_buttons(chat: TelegramChat, network: Network) -> None:
    assert chat.text("/start").status_code == 200

    sent = network.telegram_calls("sendMessage")[-1]
    assert sent["chat_id"] == str(CHAT_ID)
    assert sent["reply_markup"]["inline_keyboard"] == [
        [{"text": "I agree", "callback_data": "consent:yes"}],
        [{"text": "No thanks", "callback_data": "consent:no"}],
    ]
    assert network.sent == []  # Nothing goes out over WhatsApp.


def test_wrong_secret_is_rejected(chat: TelegramChat, network: Network) -> None:
    update = {"message": {"chat": {"id": 1, "type": "private"}, "text": "hi"}}
    assert chat.send(update, headers={}).status_code == 403
    wrong = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    assert chat.send(update, headers=wrong).status_code == 403
    assert network.telegram == []


def test_webhook_is_off_until_configured(client: TestClient) -> None:
    assert client.post("/telegram", json={}, headers=HEADERS).status_code == 404


def test_blank_secret_cannot_be_matched(make_client) -> None:
    client = make_client(telegram_bot_token=BOT_TOKEN, telegram_webhook_secret="")
    response = client.post(
        "/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""}
    )
    assert response.status_code == 404


def test_full_run_stops_at_review_without_submitting(
    chat: TelegramChat, network: Network, browser: StubBrowser
) -> None:
    chat.up_to_review()
    assert "Please check your application" in network.telegram_texts()[-1]

    chat.press("approval:approve")

    assert "Nothing has been submitted" in network.telegram_texts()[-1]
    assert browser.final_submits == 0
    assert network.telegram_calls("answerCallbackQuery")


def test_photo_is_downloaded_at_full_size_and_stored_encrypted(
    chat: TelegramChat, telegram_client: TestClient, network: Network, tmp_path
) -> None:
    chat.text("/start")
    chat.press("consent:yes")
    chat.photo()

    assert network.telegram_calls("getFile")[-1] == {"file_id": "large"}
    assert "(1 received)" in network.telegram_texts()[-1]
    stored = b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    assert b"telegram-file-bytes" not in stored


def test_pdf_document_is_accepted(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.press("consent:yes")
    chat.message(document={"file_id": "doc1", "mime_type": "application/pdf"})
    assert "(1 received)" in network.telegram_texts()[-1]


def test_other_file_types_are_refused(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.press("consent:yes")
    chat.message(document={"file_id": "doc1", "mime_type": "application/zip"})
    assert "photo or a PDF" in network.telegram_texts()[-1]


def test_captcha_image_is_sent_as_a_photo(chat: TelegramChat, network: Network) -> None:
    chat.up_to_review()
    assert [name for name, _ in network.telegram].count("sendPhoto") == 1


def test_duplicate_update_replies_once(chat: TelegramChat, network: Network) -> None:
    update = {"update_id": 5, "message": {"chat": {"id": 42, "type": "private"}, "text": "hi"}}
    chat.client.post("/telegram", json=update, headers=HEADERS)
    chat.client.post("/telegram", json=update, headers=HEADERS)
    assert len(network.telegram_calls("sendMessage")) == 1


def test_group_chats_are_ignored(chat: TelegramChat, network: Network) -> None:
    update = {"message": {"chat": {"id": -5, "type": "group"}, "text": "hi"}}
    assert chat.send(update).status_code == 200
    assert network.telegram == []


def test_start_command_does_not_answer_a_pending_question(
    chat: TelegramChat, network: Network
) -> None:
    chat.text("/start")
    chat.press("consent:yes")
    chat.photo()
    chat.press("documents:done")
    count = len(network.telegram_texts())

    chat.text("/start")

    assert len(network.telegram_texts()) == count


@pytest.mark.parametrize("word", ["STOP", "/stop"])
def test_stop_cancels_the_session(
    word: str, chat: TelegramChat, telegram_client: TestClient, network: Network
) -> None:
    chat.text("/start")
    chat.text(word)
    assert "Stopped" in network.telegram_texts()[-1]
    assert telegram_client.app.state.sessions.active_for_phone(USER_ID) is None


def test_old_button_cannot_answer_a_new_prompt(chat: TelegramChat, network: Network) -> None:
    chat.up_to_review()
    chat.press("consent:yes")
    assert "earlier message" in network.telegram_texts()[-1]


def test_receipt_is_sent_as_text_and_voice_note(
    make_client, network: Network, browser: StubBrowser
) -> None:
    client = make_client(
        telegram_bot_token=BOT_TOKEN,
        telegram_webhook_secret=SECRET,
        allow_real_submit=True,
        language_service_url=LANGUAGE_URL,
    )
    chat = TelegramChat(client)
    chat.up_to_review()
    chat.press("approval:approve")

    assert browser.final_submits == 1
    assert network.telegram_calls("sendVoice")


def test_webhook_is_registered_on_startup_when_address_is_known(
    make_client, network: Network
) -> None:
    make_client(
        telegram_bot_token=BOT_TOKEN,
        telegram_webhook_secret=SECRET,
        public_url="https://bot.example/",
    )
    assert network.telegram_calls("setWebhook") == [
        {
            "url": "https://bot.example/telegram",
            "secret_token": SECRET,
            "allowed_updates": ["message", "callback_query"],
        }
    ]


def test_failed_webhook_registration_does_not_stop_startup(
    make_client, network: Network, caplog: pytest.LogCaptureFixture
) -> None:
    network.telegram_error = "Unauthorized"
    client = make_client(
        telegram_bot_token=BOT_TOKEN,
        telegram_webhook_secret=SECRET,
        public_url="https://bot.example",
    )
    assert client.get("/health").status_code == 200
    assert "Unauthorized" in caplog.text
    assert BOT_TOKEN not in caplog.text


def test_failed_send_does_not_break_the_webhook(chat: TelegramChat, network: Network) -> None:
    network.telegram_error = "Forbidden: bot was blocked by the user"
    assert chat.text("/start").status_code == 200


def test_bot_token_and_message_text_are_not_logged(
    chat: TelegramChat, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        chat.text("/start")
        chat.press("consent:yes")
        chat.text("OTP 482913")
    assert BOT_TOKEN not in caplog.text
    assert "482913" not in caplog.text


def test_httpx_url_logging_is_off(telegram_client: TestClient) -> None:
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_voice_note_without_language_service_asks_to_type(
    chat: TelegramChat, network: Network
) -> None:
    chat.text("/start")
    chat.message(voice={"file_id": "v1", "mime_type": "audio/ogg"})
    assert "Please type" in network.telegram_texts()[-1]


def test_web_session_still_works_beside_telegram(
    telegram_client: TestClient, network: Network
) -> None:
    response = telegram_client.post(
        "/session", json={}, headers={"X-API-Key": API_TOKEN}
    )
    assert response.status_code == 200
    assert network.telegram == []


def test_extraction_is_used_over_telegram(
    chat: TelegramChat, plugins: Plugins, network: Network
) -> None:
    assert plugins.extraction is not None
    chat.up_to_review()
    assert "Full name: Demo Student" in network.telegram_texts()[-1]
