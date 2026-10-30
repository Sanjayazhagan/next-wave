"""Loads the remote teammate's modules, which may not be merged yet."""
import importlib
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Plugins:
    extraction: Callable | None = None
    rules: Callable | None = None
    doctor: Callable | None = None
    compressor: Callable | None = None


async def call(function: Callable, *args: Any) -> Any:
    """Call a plugin that may be sync or async."""
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


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
