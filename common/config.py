"""Settings for the remote modules: the process environment first, then the repo's .env.

`.env` is read, never copied into os.environ, so loading a module can't change
the settings core (or core's tests) see. Under pytest `.env` is ignored, so tests
are hermetic; live tests that need real keys load it explicitly with dotenv_values().
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values as _read

DOTENV = Path(__file__).resolve().parents[1] / ".env"


def dotenv_values() -> dict[str, str]:
    """Every non-empty value in the repo's .env."""
    if not DOTENV.is_file():
        return {}
    return {k: v for k, v in _read(DOTENV).items() if v}


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    return {} if "pytest" in sys.modules else dotenv_values()


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    return _dotenv().get(name, default)
