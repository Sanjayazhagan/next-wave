"""Shared helpers for the remote modules' tests."""
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def has_keys(*names: str) -> bool:
    """True when every name is set in the environment or the repo's .env (live tests only)."""
    import os

    from common.config import dotenv_values

    values = {**dotenv_values(), **{k: v for k, v in os.environ.items() if v}}
    return all(values.get(n) for n in names)


@pytest.fixture
def live_env(monkeypatch):
    """Load the repo's .env into the environment for one live test (tests ignore .env otherwise)."""
    from common.config import dotenv_values

    for k, v in dotenv_values().items():
        monkeypatch.setenv(k, v)
