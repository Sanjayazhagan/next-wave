import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import VERIFY_TOKEN, Chat, Network, webhook


def test_blank_app_secret_stops_startup(make_settings) -> None:
    with pytest.raises(ValidationError):
        make_settings(whatsapp_app_secret="")


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_verify_returns_challenge(client: TestClient) -> None:
    response = client.get(
        "/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 200
    assert response.text == "1158201444"


def test_verify_rejects_wrong_token(client: TestClient) -> None:
    response = client.get(
        "/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 403


def test_first_message_asks_for_consent(chat: Chat, network: Network) -> None:
    assert chat.text("Vanakkam").status_code == 200
    assert network.last_buttons() == ["consent:yes", "consent:no"]


def test_bad_signature_is_rejected(chat: Chat, network: Network) -> None:
    payload = webhook(messages=[{"from": "1", "id": "m1", "type": "text", "text": {"body": "x"}}])
    assert chat.post(payload, secret="wrong").status_code == 403
    assert network.sent == []


def test_missing_signature_is_rejected(client: TestClient, network: Network) -> None:
    assert client.post("/whatsapp", json=webhook()).status_code == 403
    assert network.sent == []


def test_duplicate_delivery_replies_once(chat: Chat, network: Network) -> None:
    message = {"from": "919000000001", "id": "same", "type": "text", "text": {"body": "hi"}}
    chat.post(webhook(messages=[message]))
    chat.post(webhook(messages=[message]))
    assert len(network.sent) == 1


def test_status_update_sends_nothing(chat: Chat, network: Network) -> None:
    payload = webhook(statuses=[{"id": "wamid.1", "status": "delivered"}])
    assert chat.post(payload).status_code == 200
    assert network.sent == []


def test_message_text_is_not_logged(
    chat: Chat, caplog: pytest.LogCaptureFixture
) -> None:
    chat.text("hi")
    chat.press("consent:yes")
    with caplog.at_level("INFO"):
        chat.text("OTP 482913")
    assert "482913" not in caplog.text


def test_settings_type_is_used(make_settings) -> None:
    assert isinstance(make_settings(), Settings)
