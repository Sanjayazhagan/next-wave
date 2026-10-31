"""The language choice, and the built-in Tamil and Hindi messages."""
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import translations
from app.graph import messages
from app.translations import BUILT_IN, HINDI, TAMIL, translate_fixed
from tests.conftest import LANGUAGE_URL, Network
from tests.test_telegram import BOT_TOKEN, SECRET, USER_ID, TelegramChat


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client(
        telegram_bot_token=BOT_TOKEN, telegram_webhook_secret=SECRET, choose_language=True
    )


@pytest.fixture
def chat(client: TestClient) -> TelegramChat:
    return TelegramChat(client)


def buttons(network: Network) -> list[dict[str, Any]]:
    rows = network.telegram_calls("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    return [button for row in rows for button in row]


def test_language_is_the_very_first_question(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    assert "Choose your language" in network.telegram_texts()[-1]
    assert [button["text"] for button in buttons(network)] == list(
        messages.LANGUAGE_CHOICES.values()
    )
    rows = network.telegram_calls("sendMessage")[-1]["reply_markup"]["inline_keyboard"]
    assert len(rows[0]) == 2  # A long list stays compact.


@pytest.mark.parametrize("code", sorted(set(messages.LANGUAGE_CHOICES) - {"en"}))
def test_every_language_on_the_menu_is_translated(
    code: str, chat: TelegramChat, network: Network
) -> None:
    chat.text("/start")
    chat.press(f"language:{code}")
    assert network.telegram_texts()[-1] == BUILT_IN[code][messages.CONSENT]
    assert buttons(network)[0]["text"] == BUILT_IN[code]["I agree"]


def test_menu_and_ai_names_cover_the_same_languages() -> None:
    assert set(messages.LANGUAGE_CHOICES) == set(messages.LANGUAGE_NAMES)


def test_choosing_tamil_shows_consent_in_tamil(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.press("language:ta")

    assert network.telegram_texts()[-1] == TAMIL[messages.CONSENT]
    assert [button["text"] for button in buttons(network)] == ["ஒப்புக்கொள்கிறேன்", "வேண்டாம்"]


def test_choosing_hindi_shows_consent_in_hindi(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.press("language:hi")
    assert network.telegram_texts()[-1] == HINDI[messages.CONSENT]


def test_choosing_english_stays_english(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.press("language:en")
    assert network.telegram_texts()[-1] == messages.CONSENT


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("Tamil", "ta"), ("हिंदी", "hi"), ("english", "en"), ("telugu", "te"), ("বাংলা", "bn")],
)
def test_language_can_be_typed(
    typed: str, expected: str, chat: TelegramChat, client: TestClient
) -> None:
    chat.text("/start")
    chat.text(typed)
    assert client.app.state.sessions.active_for_phone(USER_ID).language == expected


def test_unknown_language_asks_again(chat: TelegramChat, network: Network) -> None:
    chat.text("/start")
    chat.text("klingon")
    assert "Choose your language" in network.telegram_texts()[-1]


def test_ai_chat_is_told_the_chosen_language(chat: TelegramChat, network: Network) -> None:
    network.llm.chat_replies = [{"reply": "வணக்கம்!", "fields": {}}]
    chat.text("/start")
    chat.press("language:ta")
    chat.press("consent:yes")

    assert "USER CHOSE: Tamil" in network.llm.chat_prompts[-1]
    assert network.telegram_texts()[-1] == "வணக்கம்!"


def test_full_tamil_run_has_no_english_fixed_messages(
    chat: TelegramChat, network: Network
) -> None:
    chat.text("/start")
    chat.press("language:ta")
    chat.press("consent:yes")
    assert network.telegram_texts()[-1] == TAMIL[messages.QUESTIONS[0].text]
    chat.text("Tamil Nadu")
    chat.text("Class 12")
    chat.text("120000")
    chat.press("question_community:bc")
    confirm = network.telegram_texts()[-1]
    assert confirm.startswith(TAMIL[messages.CONFIRM_INTRO])
    assert TAMIL["Family yearly income:"] in confirm
    assert confirm.endswith(TAMIL[messages.CONFIRM_QUESTION])
    chat.press("confirm:yes")
    assert network.telegram_texts()[-1] == TAMIL[messages.DOCUMENTS]
    chat.photo()
    assert network.telegram_texts()[-1] == TAMIL[messages.DOCUMENT_RECEIVED]
    chat.press("documents:done")
    assert network.telegram_texts()[-1] == TAMIL[messages.PORTAL_ID]
    chat.text("portal-user")
    assert network.telegram_texts()[-1] == TAMIL[messages.OTP]
    chat.text("123456")
    assert network.telegram_texts()[-1] == TAMIL[messages.CAPTCHA]
    chat.text("ABCD")

    review = network.telegram_texts()[-1]
    assert review.startswith(TAMIL[messages.REVIEW_INTRO])
    assert "Demo Student" in review  # Values stay as they were entered.

    chat.press("approval:approve")
    assert network.telegram_texts()[-1] == TAMIL[messages.STOPPED_AT_REVIEW]


def test_built_in_languages_do_not_call_the_language_service(
    make_client, network: Network
) -> None:
    client = make_client(
        telegram_bot_token=BOT_TOKEN,
        telegram_webhook_secret=SECRET,
        choose_language=True,
        language_service_url=LANGUAGE_URL,
    )
    chat = TelegramChat(client)
    chat.text("/start")
    chat.press("language:hi")
    assert network.translated == []


def test_numbers_inside_messages_are_kept() -> None:
    text = messages.SUBMITTED.format(number="TN-7788")
    assert translate_fixed(text, "ta") == TAMIL[messages.SUBMITTED].format(number="TN-7788")
    assert translate_fixed(text, "hi") == HINDI[messages.SUBMITTED].format(number="TN-7788")


def test_field_labels_are_kept_inside_the_sentence() -> None:
    text = messages.FIELD_NEEDED.format(label="date of birth")
    assert "date of birth" in translate_fixed(text, "hi")
    assert "The form needs" not in translate_fixed(text, "hi")


def test_combined_messages_are_all_translated() -> None:
    earlier = messages.EARLIER_RECEIPT.format(number="R-1")
    text = f"{messages.STOPPED_AT_REVIEW}\n\n{earlier}"
    result = translate_fixed(text, "ta")
    assert TAMIL[messages.STOPPED_AT_REVIEW] in result
    assert "R-1" in result
    assert "Earlier" not in result


def test_unknown_language_is_left_alone() -> None:
    assert translate_fixed("Done", "fr") == "Done"


def english_messages() -> list[str]:
    texts = [
        value
        for name, value in vars(messages).items()
        if name.isupper()
        and isinstance(value, str)
        and name not in ("CONSENT_VERSION", "CHOOSE_LANGUAGE", "SUBMIT_UNCERTAIN")
    ]
    labels = [question.label for question in messages.QUESTIONS]
    return texts + labels + [question.text for question in messages.QUESTIONS]


@pytest.mark.parametrize("language", sorted(BUILT_IN))
def test_every_fixed_message_has_a_translation(language: str) -> None:
    missing = [text for text in english_messages() if text not in BUILT_IN[language]]
    assert missing == []


@pytest.mark.parametrize("language", sorted(BUILT_IN))
def test_translations_keep_their_placeholders(language: str) -> None:
    for english, translated in BUILT_IN[language].items():
        placeholders = re.findall(r"\{\w+\}", english)
        assert re.findall(r"\{\w+\}", translated) == placeholders, english


@pytest.mark.parametrize("language", sorted(BUILT_IN))
def test_all_languages_cover_the_same_messages(language: str) -> None:
    assert set(BUILT_IN[language]) == set(translations.TAMIL)


@pytest.mark.parametrize("language", sorted(BUILT_IN))
def test_consent_keeps_its_commands_in_every_language(language: str) -> None:
    consent = BUILT_IN[language][messages.CONSENT]
    for word in ("STOP", "/start", "OTP", "AI"):
        assert word in consent


@pytest.mark.parametrize("language", sorted(BUILT_IN))
def test_nothing_was_left_in_english(language: str) -> None:
    unchanged = [
        english
        for english, translated in BUILT_IN[language].items()
        if english == translated
    ]
    assert unchanged == []
