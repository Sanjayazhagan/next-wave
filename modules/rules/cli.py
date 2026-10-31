"""python -m modules.rules.cli --profile fixtures/profiles/me.json [--drafts]

--drafts also loads *.draft.yaml (skipping the review check, keeping the verbatim
check), so a reviewer can try a draft before approving it. Output is marked DRAFT.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from contracts.profile import Profile

from .engine import rank
from .explain import explain
from .loader import SCHEMES_DIR, load_all
from .models import Review, Scheme
from .questions import missing_questions


def _drafts() -> list[Scheme]:
    out = []
    for p in sorted((SCHEMES_DIR / "rules").glob("*.draft.yaml")):
        s = Scheme.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        out.append(s.model_copy(update={"review": Review(reviewed_by="DRAFT", reviewed_at="2000-01-01")}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--drafts", action="store_true")
    a = ap.parse_args()
    profile = Profile.model_validate_json(a.profile.read_text())
    schemes = list(load_all()) + (_drafts() if a.drafts else [])
    if a.drafts:
        print("*** DRAFT RULES INCLUDED: not reviewed ***\n")
    for m in rank(schemes, profile):
        print(f"[{m.status}] {m.name}\n  {explain(m)}")
        for c in m.also_check:
            print(f"  also check: {c.text}")
        print()
    print("Questions:")
    for q in missing_questions(schemes, profile):
        print(f"  {q.field}: {q.text_en}" + (f" {q.choices}" if q.choices else ""))


if __name__ == "__main__":
    main()
