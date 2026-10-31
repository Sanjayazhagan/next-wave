"""M3 file compressor, loaded by core through app/plugins.py.

    fit_file(data: bytes, mime_type: str, portal_id: str, document_type: str) -> bytes

Limits come from contracts/portals/<portal_id>.json. When a portal or document
has no verified spec, the file is passed through unchanged and a warning is
logged: limits are never guessed.
"""
from __future__ import annotations

import logging

from .prepare import CannotFit, Result, prepare
from .spec import NoSpec, load_portal_spec, spec_for

log = logging.getLogger(__name__)

__all__ = ["CannotFit", "NoSpec", "fit_file", "load_portal_spec", "prepare", "prepare_for_portal"]


def prepare_for_portal(data: bytes, portal_id: str, document_type: str) -> Result:
    """Raises NoSpec or CannotFit; callers that want the details (web app, doctor) use this."""
    return prepare(data, spec_for(load_portal_spec(portal_id), document_type))


def fit_file(data: bytes, mime_type: str, portal_id: str, document_type: str) -> bytes:
    """Core's plug-in entry point (called synchronously while attaching a file)."""
    try:
        result = prepare_for_portal(data, portal_id, document_type)
    except NoSpec as exc:
        log.warning("File passed through unchanged: %s", exc)
        return data
    except CannotFit as exc:
        # The portal would reject it anyway; send the original so the portal's own message shows.
        log.warning("File passed through unchanged: %s", exc)
        return data
    log.info("Prepared %s for %s: %s", document_type, portal_id, "; ".join(result.info.actions))
    return result.data
