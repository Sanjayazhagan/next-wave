"""Load reviewed rule files. Unreviewed drafts never load.

A rules file loads only if it has a `review` block and every clause appears
verbatim in the scraped snapshot of the source it cites. Together these are the
guarantee against made-up eligibility criteria.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

from .models import Scheme

SCHEMES_DIR = Path(__file__).resolve().parent / "schemes"


class RulesError(ValueError):
    pass


def _norm(s: str) -> str:
    return " ".join(s.split())


def _source_texts(scheme: Scheme, raw_dir: Path) -> dict[int, str]:
    meta_path = raw_dir / scheme.scheme_id / "meta.json"
    if not meta_path.is_file():
        raise RulesError(f"{scheme.scheme_id}: no snapshot at {meta_path}")
    meta = {m["url"]: m for m in json.loads(meta_path.read_text())}
    texts = {}
    for i, src in enumerate(scheme.sources):
        if src.url not in meta:
            raise RulesError(f"{scheme.scheme_id}: source {src.url} has no snapshot")
        texts[i] = _norm((raw_dir / scheme.scheme_id / meta[src.url]["file"]).read_text(encoding="utf-8"))
    return texts


def load_file(path: Path, raw_dir: Path | None = None) -> Scheme:
    scheme = Scheme.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if scheme.review is None:
        raise RulesError(f"{path.name}: no review block; a person must check it against its source first")
    texts = _source_texts(scheme, raw_dir or SCHEMES_DIR / "raw")
    for item in [*scheme.rules, *scheme.unmodelled]:
        if item.source not in texts:
            raise RulesError(f"{path.name}: clause cites source {item.source}, which doesn't exist")
        if _norm(item.clause) not in texts[item.source]:
            raise RulesError(f"{path.name}: clause not found verbatim in its source: {item.clause[:80]!r}")
    return scheme


@lru_cache(maxsize=1)
def load_all(rules_dir: Path | None = None) -> tuple[Scheme, ...]:
    """Every reviewed `<scheme_id>.yaml`. Drafts (`*.draft.yaml`) are skipped."""
    rules_dir = rules_dir or SCHEMES_DIR / "rules"
    return tuple(load_file(p) for p in sorted(rules_dir.glob("*.yaml")) if not p.name.endswith(".draft.yaml"))
