"""Correcting the draft at the review step, read in code (core's fake portal and chat)."""
from fastapi.testclient import TestClient

from tests.conftest import Chat, Network, session_id_for


def test_a_named_correction_is_converted_and_refilled(chat: Chat, client: TestClient, network: Network) -> None:
    chat.up_to_review()
    calls = network.llm_calls
    chat.press("approval:edit")
    chat.text("income 2 lakh")          # no item number, and money in words
    chat.text("123456")
    chat.text("ABCD")

    assert "Annual income: 200000" in network.last_text()
    profile = client.get(
        f"/session/{session_id_for(client)}", headers={"X-API-Key": "test-api-token"}
    ).json()["profile"]
    assert profile["annual_income"]["value"] == "200000"
    assert profile["annual_income"]["source_document"] == "user_edit"
    assert network.llm_calls == calls    # the correction never went to the AI


def test_an_unbelievable_value_is_asked_again(chat: Chat, network: Network) -> None:
    chat.up_to_review()
    chat.press("approval:edit")
    chat.text("date of birth 31/02/2005")   # no such date
    assert "couldn't read" in network.last_text()
