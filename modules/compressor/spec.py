"""Load portal upload specs from contracts/portals/."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from contracts.portal import DocSpec, PortalSpec

PORTALS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "portals"


class NoSpec(LookupError):
    """No verified upload limits for this portal or document."""


@lru_cache(maxsize=32)
def load_portal_spec(portal_id: str) -> PortalSpec:
    path = PORTALS_DIR / f"{portal_id}.json"
    if not path.is_file():
        raise NoSpec(f"no upload spec for portal {portal_id!r} in contracts/portals/")
    return PortalSpec.model_validate_json(path.read_text())


def spec_for(portal: PortalSpec, doc_type: str) -> DocSpec:
    """The document's own spec, else the portal-wide "*" spec."""
    for wanted in (doc_type, "*"):
        for spec in portal.documents:
            if spec.doc_type == wanted:
                return spec
    raise NoSpec(f"portal {portal.portal_id!r} has no spec for {doc_type!r}")
