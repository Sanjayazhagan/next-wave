"""Audio conversion through ffmpeg pipes."""
from __future__ import annotations

import io
import subprocess
import wave


class AudioError(RuntimeError):
    pass


def _ffmpeg(data: bytes, args: list[str]) -> bytes:
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *args],
                                input=data, capture_output=True, timeout=60)
    except FileNotFoundError as exc:
        raise AudioError("ffmpeg is not installed") from exc
    if result.returncode != 0:
        raise AudioError("ffmpeg could not convert the audio")
    return result.stdout


def to_wav16k(data: bytes) -> bytes:
    """Any audio (Telegram OGG/Opus voice notes, MP3, WAV) -> 16 kHz mono 16-bit WAV."""
    return _ffmpeg(data, ["-ac", "1", "-ar", "16000", "-sample_fmt", "s16", "-f", "wav", "pipe:1"])


def to_ogg_opus(data: bytes) -> bytes:
    """Any audio -> OGG/Opus, the format Telegram's sendVoice plays as a voice note."""
    return _ffmpeg(data, ["-vn", "-ac", "1", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"])


def duration_s(wav: bytes) -> float:
    """Duration from the WAV header. ffmpeg's piped WAV leaves the size fields unset, so use the byte count."""
    with wave.open(io.BytesIO(wav)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
    data_start = wav.find(b"data") + 8
    return round((len(wav) - data_start) / (rate * width * channels), 2)
