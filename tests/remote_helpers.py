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


@pytest.fixture(scope="module")
def real_language_url():
    """The real language service (Sarvam), in its own process on a free port. Live tests only."""
    import os
    import socket
    import subprocess
    import sys
    import time

    import httpx

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
