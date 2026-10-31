"""Loads the remote teammate's modules, which may not be merged yet."""
import asyncio
import importlib
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 240


@dataclass
class Plugins:
    extraction: Callable | None = None
    rules: Callable | None = None
    doctor: Callable | None = None
    compressor: Callable | None = None


class PluginError(Exception):
    """A module failed or timed out. The graph carries on without it."""


async def call(function: Callable, *args: Any, timeout: float = TIMEOUT_SECONDS) -> Any:
    """Call a module that may be sync or async, without freezing other chats.

    Sync modules such as OCR run in a thread, so one slow document cannot stop
    every other conversation.
    """

    async def run() -> Any:
        if inspect.iscoroutinefunction(function):
            return await function(*args)
        result = await asyncio.to_thread(function, *args)
        return await result if inspect.isawaitable(result) else result

    try:
        return await asyncio.wait_for(run(), timeout)
    except Exception as exc:
        # The type only: a message or traceback could repeat document contents.
        name = getattr(function, "__name__", type(function).__name__)
        log.error("Module %s failed: %s", name, type(exc).__name__)
        raise PluginError(f"{name}: {type(exc).__name__}") from exc


def _load(module_name: str, function_name: str) -> Callable | None:
    try:
        module = importlib.import_module(f"modules.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name in ("modules", f"modules.{module_name}"):
            log.info("Module %s is not merged, so it is skipped", module_name)
            return None
        log.exception("Module %s failed to import, so it is skipped", module_name)
        return None
    except Exception:
        log.exception("Module %s failed to import, so it is skipped", module_name)
        return None
    return getattr(module, function_name, None)


def load_plugins() -> Plugins:
    return Plugins(
        extraction=_load("extraction", "extract"),
        rules=_load("rules", "rank_schemes"),
        doctor=_load("doctor", "check_application"),
        compressor=_load("compressor", "fit_file"),
    )
