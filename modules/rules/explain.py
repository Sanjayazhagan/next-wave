"""Fixed-template explanations with the cited clause. No LLM."""
from __future__ import annotations

from .models import SchemeMatch


def _label(field: str) -> str:
    return {"annual_income": "family income", "govt_school_6_to_12": "schooling (Class 6 to 12)",
            "disability_percent": "disability percentage"}.get(field, field.replace("_", " "))


def explain(m: SchemeMatch) -> str:
    if m.status == "eligible":
        r = m.results[0] if m.results else None
        parts = [f"You qualify for {m.name}."]
        if m.benefit_text:
            parts.append(f"Benefit: {m.benefit_text}")
        if m.deadline:
            parts.append(f"Last date: {m.deadline.strftime('%d %b %Y')}.")
        if r:
            parts.append(f'Rule: "{r.clause.text}" (source: {r.clause.source_url})')
        return " ".join(parts)
    if m.status == "not_eligible":
        r = next(r for r in m.results if r.status == "fail")
        return (f"You don't qualify for {m.name} because your {_label(r.field)} is {r.actual}, and the rule needs "
                f'{r.expected}. Rule: "{r.clause.text}" (source: {r.clause.source_url})')
    fields = sorted({("exact " if r.actual else "") + _label(r.field) for r in m.results if r.status == "unknown"})
    return f"To check {m.name}, I need your {', '.join(fields)}."


def cited_clause(m: SchemeMatch) -> str:
    """One line for core's SchemeMatch.cited_clause (shown under the scheme's name)."""
    if m.status == "needs_info":
        passed = next((r for r in m.results if r.status == "pass"), None)
        need = explain(m)
        return f'{need} Matched so far: "{passed.clause.text}" ({passed.clause.source_url})' if passed else need
    r = m.results[0] if m.results else None
    return f'"{r.clause.text}" ({r.clause.source_url})' if r else m.name
