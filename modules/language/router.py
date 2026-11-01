"""Pick a provider per operation, retry once, then fall back to the other provider."""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from common.config import env

from . import protect
from .providers.base import Provider, ProviderError

log = logging.getLogger(__name__)


class AllProvidersFailed(RuntimeError):
    def __init__(self, op: str, errors: dict[str, str]) -> None:
        super().__init__(f"{op} failed on every provider")
        self.errors = errors


@dataclass
class Health:
    ok: bool | None = None
    last_latency_ms: int | None = None
    last_error: str | None = None


@dataclass
class Router:
    providers: dict[str, Provider]
    health: dict[str, Health] = field(default_factory=dict)

    def order(self, op: str) -> list[Provider]:
        """Primary first (STT_PRIMARY for speech-to-text, else LANG_PRIMARY); unconfigured providers dropped."""
        primary = (env("STT_PRIMARY") if op == "stt" else None) or env("LANG_PRIMARY", "bhashini")
        names = sorted(self.providers, key=lambda n: n != primary)
        return [self.providers[n] for n in names if self.providers[n].configured()]

    async def run(self, op: str, call: Callable[[Provider], Awaitable[Any]],
                  providers: list[Provider] | None = None) -> tuple[Any, str, int]:
        """Return (result, provider name, latency ms). The first provider gets one retry before the next."""
        errors: dict[str, str] = {}
        providers = self.order(op) if providers is None else providers
        if not providers:
            raise AllProvidersFailed(op, {"config": "no language provider has its keys set"})
        for i, provider in enumerate(providers):
            for _ in range(2 if i == 0 else 1):
                t0 = time.perf_counter()
                try:
                    result = await call(provider)
                except (ProviderError, ValueError) as exc:
                    errors[provider.name] = str(exc)
                    self._record(provider.name, False, t0, str(exc))
                    continue
                ms = self._record(provider.name, True, t0, None)
                return result, provider.name, ms
        raise AllProvidersFailed(op, errors)

    def _record(self, name: str, ok: bool, t0: float, error: str | None) -> int:
        ms = round((time.perf_counter() - t0) * 1000)
        self.health[name] = Health(ok=ok, last_latency_ms=ms, last_error=error)
        return ms

    async def translate(self, text: str, src: str, tgt: str, keep: list[str]) -> tuple[str, str, int]:
        """Translate with protected terms. If a provider drops a token, the next provider is tried."""
        masked, originals = protect.mask(text, keep)
        t0 = time.perf_counter()
        remaining = self.order("translate")
        best: tuple[str, list[str], str] | None = None
        while remaining:
            try:
                out, name, _ = await self.run("translate", lambda p: p.translate(masked, src, tgt), remaining)
            except AllProvidersFailed:
                if best is None:
                    raise
                break
            restored, missing = protect.unmask(out, originals)
            if best is None or len(missing) < len(best[1]):
                best = (restored, missing, name)
            if not missing:
                break
            remaining = remaining[[p.name for p in remaining].index(name) + 1:]
        if best is None:
            raise AllProvidersFailed("translate", {"config": "no language provider has its keys set"})
        restored, missing, name = best
        if missing:
            # Every provider lost a token, which can leave a stray "0" where an amount was
            # ("income is 0."). Translating the plain text is safer: amounts survive, though
            # a scheme name may get translated.
            log.warning("translation dropped %d protected terms; translated without them", len(missing))
            restored, name, _ = await self.run("translate", lambda p: p.translate(text, src, tgt))
        return restored, name, round((time.perf_counter() - t0) * 1000)
