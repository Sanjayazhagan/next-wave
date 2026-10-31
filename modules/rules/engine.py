"""Plain-Python eligibility. No LLM runs at decision time."""
from __future__ import annotations

from datetime import date

from common.fields import COMMUNITY_BUTTONS
from common.textnorm import norm_amount, norm_category, norm_text
from contracts.profile import Profile

from .models import Clause, Rule, RuleResult, Scheme, SchemeMatch

NUMERIC_OPS = {"lt", "lte", "gt", "gte", "between"}
STATE_BACKWARD = {"BC", "BCM", "MBC", "DNC"}
_GENDER = {"female": {"female", "f", "girl", "woman", "pen", "பெண்"}, "male": {"male", "m", "boy", "man", "aan", "ஆண்"},
           "transgender": {"transgender", "third gender", "other"}}
_STATES = {"tn": "tamil nadu", "tamilnadu": "tamil nadu", "tamil nadu": "tamil nadu", "தமிழ்நாடு": "tamil nadu",
           "ap": "andhra pradesh", "ka": "karnataka", "kl": "kerala", "up": "uttar pradesh", "mh": "maharashtra"}
_YES = {"yes", "y", "true", "ஆம்"}
_NO = {"no", "n", "false", "இல்லை"}


def _clause(scheme: Scheme, text: str, source: int) -> Clause:
    src = scheme.sources[source]
    return Clause(text=text, source_url=src.url, scraped_at=src.scraped_at)


def _expected(rule: Rule) -> str:
    sym = {"eq": "=", "ne": "≠", "lt": "<", "lte": "≤", "gt": ">", "gte": "≥"}
    if rule.op in sym:
        return f"{sym[rule.op]} {rule.value}"
    if rule.op == "between":
        return f"between {rule.value[0]} and {rule.value[1]}"
    if rule.op in ("in", "contains_any"):
        return ("one of " if rule.op == "in" else "mentions one of ") + ", ".join(map(str, rule.value))
    return "not one of " + ", ".join(map(str, rule.value))


def _gender(s: str) -> str | None:
    t = norm_text(s)
    return next((g for g, words in _GENDER.items() if t in words), None)


def _candidates(field: str, raw: str) -> set[str] | None:
    """Possible normalised values. Core's community buttons stand for several categories."""
    if field == "community":
        # Core's buttons store exactly "bc", "sc_st" or "general"; a document gives a code such as "BC".
        if raw.strip() in COMMUNITY_BUTTONS:
            return COMMUNITY_BUTTONS[raw.strip()]
        code = norm_category(raw)
        return {code} if code else None
    if field == "gender":
        g = _gender(raw)
        return {g} if g else None
    t = norm_text(raw)
    if field == "state":
        return {_STATES.get(t, t)}
    if t in _YES:
        return {"yes"}
    if t in _NO:
        return {"no"}
    return {t}


def _norm_expected(field: str, v: object) -> str:
    if field == "community":
        return norm_category(str(v)) or str(v).upper()
    if field == "gender":
        return _gender(str(v)) or norm_text(str(v))
    if field == "state":
        return _STATES.get(norm_text(str(v)), norm_text(str(v)))
    return norm_text(str(v))


def _test_one(rule: Rule, actual: str) -> bool:
    exp = rule.value
    if rule.op == "eq":
        return actual == _norm_expected(rule.field, exp)
    if rule.op == "ne":
        return actual != _norm_expected(rule.field, exp)
    if rule.op == "in":
        return actual in {_norm_expected(rule.field, v) for v in exp}
    if rule.op == "not_in":
        return actual not in {_norm_expected(rule.field, v) for v in exp}
    if rule.op == "contains_any":
        return any(norm_text(str(v)) in actual for v in exp)
    raise ValueError(rule.op)


def evaluate(scheme: Scheme, rule: Rule, profile: Profile) -> RuleResult:
    field = profile.fields.get(rule.field)
    raw = field.value if field else None
    clause = _clause(scheme, rule.clause, rule.source)

    def result(status: str) -> RuleResult:
        return RuleResult(rule_id=rule.id, field=rule.field, status=status, expected=_expected(rule),
                          actual=raw, clause=clause)

    if raw is None or not str(raw).strip():
        return result("unknown")
    if rule.op in NUMERIC_OPS:
        n = norm_amount(raw)
        if n is None:
            try:
                n = float(raw)
            except ValueError:
                return result("unknown")
        ok = {"lt": lambda: n < rule.value, "lte": lambda: n <= rule.value, "gt": lambda: n > rule.value,
              "gte": lambda: n >= rule.value, "between": lambda: rule.value[0] <= n <= rule.value[1]}[rule.op]()
        return result("pass" if ok else "fail")
    candidates = _candidates(rule.field, raw)
    if not candidates:
        return result("unknown")
    if rule.field == "community" and candidates == {"OBC"} and rule.op in ("in", "eq"):
        listed = {_norm_expected("community", v) for v in (rule.value if rule.op == "in" else [rule.value])}
        if "OBC" not in listed and listed & STATE_BACKWARD:
            # A central OBC certificate doesn't say which state category (BC, MBC, DNC) applies.
            return result("unknown")
    outcomes = {_test_one(rule, c) for c in candidates}
    # A grouped answer (e.g. "BC / MBC") passes only if every member passes.
    return result("pass" if outcomes == {True} else "fail" if outcomes == {False} else "unknown")


def match(scheme: Scheme, profile: Profile, today: date | None = None) -> SchemeMatch:
    results = [evaluate(scheme, r, profile) for r in scheme.rules]
    today = today or date.today()
    if scheme.deadline and scheme.deadline < today:
        results.append(RuleResult(rule_id="deadline", field="deadline", status="fail",
                                  expected=f"apply by {scheme.deadline.isoformat()}", actual=today.isoformat(),
                                  clause=_clause(scheme, scheme.deadline_clause or f"Last date: {scheme.deadline}", 0)))
    statuses = {r.status for r in results}
    status = "not_eligible" if "fail" in statuses else "needs_info" if "unknown" in statuses else "eligible"
    return SchemeMatch(scheme_id=scheme.scheme_id, name=scheme.name, portal_id=scheme.portal_id, status=status,
                       results=results, also_check=[_clause(scheme, u.clause, u.source) for u in scheme.unmodelled],
                       benefit_inr=scheme.benefit_inr, benefit_text=scheme.benefit_text, deadline=scheme.deadline,
                       required_docs=scheme.required_docs)


_ORDER = {"eligible": 0, "needs_info": 1, "not_eligible": 2}


def rank(schemes: tuple[Scheme, ...] | list[Scheme], profile: Profile, today: date | None = None) -> list[SchemeMatch]:
    """Eligible first, then needs_info, then not_eligible; then highest benefit, then nearest deadline."""
    matches = [match(s, profile, today) for s in schemes]
    return sorted(matches, key=lambda m: (_ORDER[m.status], -(m.benefit_inr or 0), m.deadline or date.max))
