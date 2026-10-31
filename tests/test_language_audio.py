import io
import wave

import numpy as np

from modules.language.audio import duration_s, to_ogg_opus, to_wav16k
from tests.remote_helpers import needs_ffmpeg


def _sine_wav(seconds=1.0, rate=44100) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    pcm = (np.sin(2 * np.pi * 440 * t) * 12000).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def test_duration_from_header():
    assert duration_s(_sine_wav(2.0, 16000)) == 2.0


@needs_ffmpeg
def test_wav_to_ogg_and_back_keeps_duration():
    ogg = to_ogg_opus(_sine_wav())
    assert ogg[:4] == b"OggS"
    wav = to_wav16k(ogg)
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
    assert abs(duration_s(wav) - 1.0) < 0.1
