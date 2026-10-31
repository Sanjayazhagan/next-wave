"""ISO 639-1 codes (what core uses) to each provider's codes."""

SARVAM = {"en": "en-IN", "ta": "ta-IN", "hi": "hi-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN",
          "bn": "bn-IN", "mr": "mr-IN", "gu": "gu-IN", "pa": "pa-IN", "or": "od-IN", "ur": "ur-IN"}
SARVAM_TO_ISO = {v: k for k, v in SARVAM.items()}
# Sarvam's text-to-speech covers fewer languages than its other APIs.
SARVAM_TTS = {"en", "ta", "hi", "te", "kn", "ml", "bn", "mr", "gu", "pa", "or"}


def to_sarvam(code: str) -> str:
    try:
        return SARVAM[code]
    except KeyError:
        raise ValueError(f"language {code!r} not supported by Sarvam") from None


def from_sarvam(code: str | None) -> str | None:
    return SARVAM_TO_ISO.get(code or "")
