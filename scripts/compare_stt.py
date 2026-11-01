"""Run every fixtures/voice/*.ogg through each configured STT provider and print a table.

Use it to choose STT_PRIMARY: Tamil-English mixed speech is the main risk.
    uv run python -m scripts.compare_stt [--lang ta] [--sarvam-modes transcribe,codemix]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

import httpx

from modules.language.audio import to_wav16k
from modules.language.providers.base import ProviderError
from modules.language.providers.bhashini import Bhashini
from modules.language.providers.sarvam import Sarvam

VOICE = Path(__file__).resolve().parents[1] / "fixtures" / "voice"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=None, help="language hint; omit for auto-detect where supported")
    ap.add_argument("--sarvam-modes", default="transcribe,codemix")
    a = ap.parse_args()
    files = sorted(VOICE.glob("*.ogg"))
    if not files:
        raise SystemExit(f"no voice notes in {VOICE}")
    async with httpx.AsyncClient() as http:
        runs = []
        bh = Bhashini(http)
        if bh.configured():
            runs.append(("bhashini", bh, None))
        sv = Sarvam(http)
        if sv.configured():
            runs += [(f"sarvam:{m}", sv, m) for m in a.sarvam_modes.split(",")]
        if not runs:
            raise SystemExit("no provider keys set in .env")
        print(f"{'file':28} {'provider':18} {'ms':>6}  lang  transcript")
        for f in files:
            wav = to_wav16k(f.read_bytes())
            for label, provider, mode in runs:
                if mode:
                    os.environ["SARVAM_STT_MODE"] = mode
                t0 = time.perf_counter()
                try:
                    text, lang = await provider.stt(wav, a.lang)
                except ProviderError as exc:
                    text, lang = f"ERROR {exc}", "-"
                ms = round((time.perf_counter() - t0) * 1000)
                print(f"{f.name:28} {label:18} {ms:>6}  {lang:4}  {text}")


if __name__ == "__main__":
    asyncio.run(main())
