import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.conversation import _voice_reply


def run(pending_kind: str, detected: str) -> MagicMock:
    sessions = MagicMock()
    language = SimpleNamespace(
        available=True,
        speech_to_text=AsyncMock(return_value=SimpleNamespace(text="BC", language=detected)),
        translate=AsyncMock(return_value="BC"),
    )
    ctx = SimpleNamespace(
        language=language,
        sessions=sessions,
        settings=SimpleNamespace(max_upload_bytes=1000),
        downloader=SimpleNamespace(download_media=AsyncMock(return_value=(b"a", "audio/ogg"))),
    )
    session = SimpleNamespace(id="s1", pending_kind=pending_kind)
    asyncio.run(_voice_reply(SimpleNamespace(media_id="m1"), session, ctx))
    return sessions


@pytest.mark.parametrize("kind", ["language", "question", "confirm", "chat"])
def test_a_voice_note_never_changes_the_selected_language(kind: str) -> None:
    run(kind, "en").set_language.assert_not_called()
