"""A whole Telegram conversation answered by voice, through the real language service and Sarvam.

Only Telegram's servers are faked (they hand over the voice-note files). Needs a Sarvam key in
.env and the voice notes in fixtures/voice/; skipped otherwise.
"""
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from tests.conftest import LANGUAGE_URL, Network
from tests.remote_helpers import FIXTURES, has_keys, needs_ffmpeg
from tests.test_telegram import BOT_TOKEN, SECRET, USER_ID, TelegramChat

VOICE = FIXTURES / "voice"
NOTES = {name: VOICE / f"{name}.ogg" for name in ("2_state_course", "3_income")}

pytestmark = [pytest.mark.live, needs_ffmpeg,
              pytest.mark.skipif(not has_keys("SARVAM_API_KEY"), reason="no Sarvam key"),
              pytest.mark.skipif(not all(p.exists() for p in NOTES.values()), reason="no fixtures/voice notes")]


@pytest.fixture(scope="module")
def language_url():
    """The real language service, in its own process, on a free port."""
    from common.config import dotenv_values

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, **dotenv_values(), "LANG_PRIMARY": "sarvam", "STT_PRIMARY": "sarvam",
           "SARVAM_STT_MODE": "codemix"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "modules.language.app:app", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def test_a_conversation_answered_by_voice(make_client, network: Network, language_url: str) -> None:
    heard = []

    def real_language(request: httpx.Request) -> httpx.Response:
        reply = httpx.request(request.method, language_url + request.url.path, content=request.content,
                              headers={"content-type": "application/json"}, timeout=60)
        if request.url.path == "/translate":
            heard.append(reply.json()["text"])
        return httpx.Response(reply.status_code, content=reply.content,
                              headers={"content-type": "application/json"})

    network._language = real_language
    client = make_client(telegram_bot_token=BOT_TOKEN, telegram_webhook_secret=SECRET,
                         language_service_url=LANGUAGE_URL, allow_real_submit=True)
    chat = TelegramChat(client)

    def say(note: str) -> None:
        network.telegram_file = NOTES[note].read_bytes()
        chat.message(voice={"file_id": note, "mime_type": "audio/ogg"})

    chat.text("/start")
    chat.press("consent:yes")
    say("2_state_course")                       # "நான் தமிழ்நாட்டில் இருக்கிறேன். BE முதல் ஆண்டு படிக்கிறேன்."
    assert any("Tamil Nadu" in text for text in heard)
    assert any("஀" <= ch <= "௿" for ch in network.telegram_texts()[-1])   # the bot now writes Tamil
    chat.text("Class 12")
    say("3_income")                             # "எங்கள் குடும்ப ஆண்டு வருமானம் ₹2,00,000."
    chat.press("question_community:bc")
    chat.press("confirm:yes")

    session_id = client.app.state.sessions.active_for_phone(USER_ID).id
    profile = client.get(f"/session/{session_id}", headers={"X-API-Key": "test-api-token"}).json()["profile"]
    assert profile["state"]["value"] == "Tamil Nadu"
    assert profile["annual_income"]["value"] == "200000"      # digits, not the spoken sentence

    chat.photo()
    chat.press("documents:done")
    chat.text("portal-user")
    chat.text("123456")
    chat.text("ABCD")
    chat.press("approval:approve")
    assert network.telegram_calls("sendVoice"), "the receipt should also arrive as a Tamil voice note"
