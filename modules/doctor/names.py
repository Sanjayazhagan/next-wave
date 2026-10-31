"""Compare names the way Tamil Nadu documents write them (initials, order, honorifics)."""
from __future__ import annotations

from rapidfuzz import fuzz

from common.textnorm import norm_text

HONORIFICS = {"mr", "ms", "mrs", "miss", "selvan", "selvi", "thiru", "thirumathi", "tmt", "kumari", "kum", "dr", "smt", "sri", "shri"}
CONSISTENT = 95
MINOR = 85


def canon(name: str) -> list[str]:
    """Tokens without honorifics; dots split initials ('S.Satyajit' -> ['s', 'satyajit'])."""
    tokens = norm_text(name.replace(".", " ")).split()
    return [t for t in tokens if t not in HONORIFICS]


def _initials_match(a: list[str], b: list[str], father: list[str]) -> bool:
    """Each initial in one name matches a full token in the other, or the father's name."""
    a_init, a_full = [t for t in a if len(t) == 1], [t for t in a if len(t) > 1]
    b_init, b_full = [t for t in b if len(t) == 1], [t for t in b if len(t) > 1]
    if not (a_init or b_init) or not a_full or not b_full:
        return False
    # The full tokens one side has must be found on the other side as tokens or initials.
    for full, other_full, other_init, own_init in ((a_full, b_full, b_init, a_init), (b_full, a_full, a_init, b_init)):
        for t in full:
            if t not in other_full and t[0] not in other_init:
                return False
        firsts = {t[0] for t in other_full} | {t[0] for t in father}
        if any(i not in firsts for i in own_init):
            return False
    return True


def compare(a: str, b: str, father: str | None = None) -> tuple[int, str]:
    """Return (score 0-100, note)."""
    ta, tb = canon(a), canon(b)
    if not ta or not tb:
        return 0, "name missing"
    if sorted(ta) == sorted(tb):
        return 100, "same name"
    if _initials_match(ta, tb, canon(father or "")):
        return 92, "initials expanded"
    score = int(fuzz.token_set_ratio(" ".join(t for t in ta if len(t) > 1), " ".join(t for t in tb if len(t) > 1)))
    return score, "minor spelling difference" if score >= MINOR else "different names"
