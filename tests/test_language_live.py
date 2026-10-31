"""Live calls to the real providers. Skipped without keys or voice fixtures."""
import asyncio

import httpx
import pytest

from modules.language.audio import to_wav16k
from modules.language.providers.bhashini import Bhashini
from modules.language.providers.sarvam import Sarvam
from tests.remote_helpers import FIXTURES, has_keys, live_env, needs_ffmpeg  # noqa: F401 (fixture)

VOICE = sorted((FIXTURES / "voice").glob("*.ogg"))[:2] if (FIXTURES / "voice").is_dir() else []
PROVIDERS = [p for p, keys in ((Sarvam, ["SARVAM_API_KEY"]),
                               (Bhashini, ["BHASHINI_USER_ID", "BHASHINI_ULCA_API_KEY", "BHASHINI_PIPELINE_ID"]))
             if has_keys(*keys)]

pytestmark = [pytest.mark.live, needs_ffmpeg, pytest.mark.skipif(not PROVIDERS, reason="no provider keys"),
              pytest.mark.usefixtures("live_env")]


@pytest.mark.parametrize("provider_cls", PROVIDERS)
@pytest.mark.skipif(not VOICE, reason="no fixtures/voice/*.ogg")
def test_stt_on_voice_notes(provider_cls):
    async def go():
        async with httpx.AsyncClient() as http:
            p = provider_cls(http)
            return [await p.stt(to_wav16k(f.read_bytes()), None) for f in VOICE]
    for text, lang in asyncio.run(go()):
        assert text.strip() and lang


@pytest.mark.parametrize("provider_cls", PROVIDERS)
def test_tts_converts_to_voice_note(provider_cls):
    from modules.language.audio import to_ogg_opus

    async def go():
        async with httpx.AsyncClient() as http:
            return await provider_cls(http).tts("வணக்கம், உங்கள் விண்ணப்பம் தயாராக உள்ளது.", "ta", None)
    audio, _ = asyncio.run(go())
    assert to_ogg_opus(audio)[:4] == b"OggS"
