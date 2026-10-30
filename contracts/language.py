"""Language API: language service <-> core. JSON bodies, base64 audio."""
from pydantic import BaseModel


class SttRequest(BaseModel):  # POST /stt
    audio_base64: str
    mime_type: str  # WhatsApp voice notes are "audio/ogg; codecs=opus".


class SttResponse(BaseModel):
    text: str
    language: str  # ISO 639-1, for example "ta".


class TranslateRequest(BaseModel):  # POST /translate
    text: str
    source: str
    target: str


class TranslateResponse(BaseModel):
    text: str


class TtsRequest(BaseModel):  # POST /tts
    text: str
    language: str


class TtsResponse(BaseModel):
    audio_base64: str  # Any format ffmpeg reads; core converts it to OGG/Opus.
    mime_type: str
