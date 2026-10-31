"""Draft a rules file from a scheme's scraped text with the team LLM (one call per scheme).

    uv run python -m modules.rules.draft_rules <scheme_id> [...]

Writes schemes/rules/<scheme_id>.draft.yaml. Drafts never load: a person checks
every value against the source, adds a `review:` block and renames the file.
Rules whose clause is not verbatim in the source are dropped and listed.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import yaml
from pydantic import BaseModel

from common.fields import FIELD_KEYS
from common.llm import text_json

from .loader import SCHEMES_DIR, _norm
from .models import Op
from .scrape import load_sources

EXTRA_FIELDS = ["disability_percent", "govt_school_6_to_12"]

SYSTEM = (
    "You turn official Indian scholarship guidelines into machine-checkable eligibility rules. "
    f"Use only these profile fields: {', '.join(FIELD_KEYS + EXTRA_FIELDS)}. "
    "Allowed ops: eq, ne, in, not_in, lt, lte, gt, gte, between, contains_any. "
    "Copy every `clause` verbatim, character for character, from the source text. "
    "Amounts are integer rupees per year. community values are codes: SC, SCA, ST, BC, BCM, MBC, DNC, OBC, EWS, OC. "
    "gender values: female, male, transgender. If a criterion can't be expressed with these fields and ops, put it "
    "under `unmodelled` with its verbatim clause instead of forcing it. Never use knowledge from outside the text."
)


class DraftRule(BaseModel):
    id: str
    field: str
    op: Op
    value: Any
    clause: str
    source: int = 0


class DraftUnmodelled(BaseModel):
    clause: str
    source: int = 0


class Draft(BaseModel):
    benefit_inr: int | None = None
    benefit_text: str | None = None
    deadline: str | None = None
    required_docs: list[str] = []
    rules: list[DraftRule]
    unmodelled: list[DraftUnmodelled] = []


def draft(scheme_id: str) -> None:
    src = next(s for s in load_sources() if s["scheme_id"] == scheme_id)
    raw = SCHEMES_DIR / "raw" / scheme_id
    meta = {m["url"]: m for m in json.loads((raw / "meta.json").read_text())}
    sources = [{"url": u, "scraped_at": meta[u]["scraped_at"]} for u in src["urls"] if u in meta]
    texts = [(raw / meta[s["url"]]["file"]).read_text(encoding="utf-8") for s in sources]
    prompt = (f"Scheme: {src['name']}\nrequired_docs must use: marksheet, income, community.\n\n"
              + "\n\n".join(f"--- SOURCE {i} ({s['url']}) ---\n{t}" for i, (s, t) in enumerate(zip(sources, texts))))
    d = text_json(prompt, Draft, caller="rules.draft", system=SYSTEM)

    norm_texts = [_norm(t) for t in texts]
    kept, dropped = [], []
    for item in [*d.rules, *d.unmodelled]:
        ok = item.source < len(norm_texts) and _norm(item.clause) in norm_texts[item.source]
        (kept if ok else dropped).append(item)
    out = {
        "scheme_id": scheme_id, "name": src["name"], "portal_id": src["portal_id"],
        "benefit_inr": d.benefit_inr, "benefit_text": d.benefit_text, "deadline": d.deadline,
        "required_docs": d.required_docs, "sources": sources,
        "rules": [r.model_dump() for r in kept if isinstance(r, DraftRule)],
        "unmodelled": [u.model_dump() for u in kept if isinstance(u, DraftUnmodelled)],
    }
    path = SCHEMES_DIR / "rules" / f"{scheme_id}.draft.yaml"
    header = f"# DRAFT by {__name__}, not loaded. Review against raw/{scheme_id}/, add `review:`, rename.\n"
    if dropped:
        header += "# Dropped (clause not verbatim in source):\n" + "".join(f"#   {x.clause[:100]}\n" for x in dropped)
    path.write_text(header + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    print(f"wrote {path} ({len(out['rules'])} rules, {len(dropped)} dropped)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scheme_ids", nargs="+")
    for sid in ap.parse_args().scheme_ids:
        draft(sid)
