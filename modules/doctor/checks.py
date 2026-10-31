"""One function per check. Each returns a list of findings (empty when all is well)."""
from __future__ import annotations

from datetime import date
from itertools import combinations

from common.textnorm import norm_amount, norm_category, norm_date, norm_text
from contracts.documents import ExtractedDocument
from contracts.portal import DocSpec, PreparedFile
from contracts.profile import Profile

from . import messages as msg
from . import names
from .models import POINTS, Finding, Severity

VERIFIED_CONF = 0.8
NAME_FIELDS = ("full_name",)
CROSS_FIELDS = ("date_of_birth", "father_name", "community", "annual_income")
# Which document is authoritative for a field when documents disagree.
AUTHORITY = {"annual_income": "income", "community": "community"}


def _finding(check: str, kind: str, field: str | None, severity: Severity, detail: str, fix: str,
             values: dict[str, str] | None = None) -> Finding:
    return Finding(check=check, kind=kind, field=field, severity=severity, points=POINTS[severity], detail=detail,
                   fix=fix, values_by_doc=values or {})


def parent_held(docs: list[ExtractedDocument]) -> set[int]:
    """Indexes of income certificates issued in a parent's name (common: the family income is the parent's).

    Detected when the certificate's holder matches the father's name on another document.
    """
    fathers = [d.fields["father_name"].value for d in docs if d.document_type != "income" and "father_name" in d.fields]
    out = set()
    for i, d in enumerate(docs):
        holder = d.fields.get("full_name")
        if d.document_type == "income" and holder and any(
                names.compare(holder.value, f)[0] >= names.MINOR for f in fathers):
            out.add(i)
    return out


def _student_docs(docs: list[ExtractedDocument]) -> list[ExtractedDocument]:
    """Documents about the student themself (parent-held income certificates left out)."""
    skip = parent_held(docs)
    return [d for i, d in enumerate(docs) if i not in skip]


def _values(docs: list[ExtractedDocument], field: str) -> dict[str, str]:
    """Document type -> value. Never includes Aadhaar or bank fields (they aren't compared)."""
    return {d.document_type: d.fields[field].value for d in docs if field in d.fields and d.fields[field].value}


def name_consistency(docs: list[ExtractedDocument]) -> list[Finding]:
    out = []
    docs = _student_docs(docs)
    father = next(iter(_values(docs, "father_name").values()), None)
    for field in NAME_FIELDS:
        vals = _values(docs, field)
        for (da, a), (db, b) in combinations(vals.items(), 2):
            score, note = names.compare(a, b, father)
            if score >= names.CONSISTENT:
                continue
            sev: Severity = "medium" if score >= names.MINOR else "high"
            out.append(_finding("name_consistency", "mismatch", field, sev, f"{note} (similarity {score})",
                                msg.name_mismatch(field, da, a, db, b), {da: a, db: b}))
    return out


def _same(field: str, a: str, b: str, father: str | None) -> bool:
    if field == "father_name":
        return names.compare(a, b)[0] >= names.CONSISTENT
    if field == "date_of_birth":
        return norm_date(a) is not None and norm_date(a) == norm_date(b)
    if field == "community":
        return (norm_category(a) or norm_text(a)) == (norm_category(b) or norm_text(b))
    if field == "annual_income":
        return norm_amount(a) == norm_amount(b)
    return norm_text(a) == norm_text(b)


def field_consistency(docs: list[ExtractedDocument]) -> list[Finding]:
    out = []
    student = _student_docs(docs)
    for field in CROSS_FIELDS:
        # A parent-held income certificate still counts for income, not for names or dates of birth.
        vals = _values(docs if field == "annual_income" else student, field)
        if len(vals) < 2:
            continue
        items = list(vals.items())
        if all(_same(field, items[0][1], v, None) for _, v in items[1:]):
            continue
        winner = AUTHORITY.get(field) if AUTHORITY.get(field) in vals else None
        out.append(_finding("field_consistency", "mismatch", field, "high", f"{field} differs between documents",
                            msg.field_mismatch(field, vals, winner), vals))
    return out


def verified_profile(profile: Profile) -> Profile:
    """Fields a person gave or confirmed, or that documents read with high confidence."""
    return Profile(fields={k: f for k, f in profile.fields.items()
                           if f.source_document.startswith("user_") or f.confidence >= VERIFIED_CONF})


def eligibility_recheck(profile: Profile, scheme) -> list[Finding]:
    from modules.rules.engine import match
    from modules.rules.explain import explain

    m = match(scheme, verified_profile(profile))
    if m.status == "not_eligible":
        r = next(r for r in m.results if r.status == "fail")
        reason = f'your {r.field.replace("_", " ")} is {r.actual}, and the rule needs {r.expected} ("{r.clause.text}").'
        return [_finding("eligibility_recheck", "eligibility", r.field, "blocker", explain(m),
                         msg.not_eligible(m.name, reason))]
    if m.status == "needs_info":
        unknown = [r for r in m.results if r.status == "unknown"]
        if any(r.field == "community" and r.actual == "OBC" for r in unknown):
            return [_finding("eligibility_recheck", "eligibility", "community", "medium", explain(m),
                             msg.state_community(m.name))]
        fields = sorted({r.field.replace("_", " ") for r in unknown})
        return [_finding("eligibility_recheck", "eligibility", None, "medium", explain(m), msg.needs_info(m.name, fields))]
    return []


def required_docs(docs: list[ExtractedDocument], scheme) -> list[Finding]:
    if not docs:
        # Nothing was read automatically, so absence proves nothing; ask for a manual check instead.
        return [_finding("required_docs", "missing_doc", None, "medium", "no document could be read automatically",
                         "I couldn't read your documents automatically. Please check you uploaded: "
                         + ", ".join(msg.doc(d) for d in scheme.required_docs) + ".")]
    present = {d.document_type for d in docs}
    return [_finding("required_docs", "missing_doc", None, "blocker", f"{d} not uploaded", msg.missing_doc(d, scheme.name))
            for d in scheme.required_docs if d not in present]


def file_spec(prepared: dict[str, PreparedFile], specs: dict[str, DocSpec]) -> list[Finding]:
    """Prepared files (from the compressor) against the portal's limits."""
    out = []
    for doc_type, pf in prepared.items():
        spec = specs.get(doc_type) or specs.get("*")
        if spec is None:
            continue
        accepted = {"image/jpeg" if t in ("jpg", "jpeg") else "image/png" if t == "png" else "application/pdf"
                    for t in spec.accepted_types}
        problems = []
        if pf.mime not in accepted:
            problems.append(f"is {pf.mime}, but the portal accepts {', '.join(spec.accepted_types)}")
        if pf.size_kb > spec.max_kb:
            problems.append(f"is {pf.size_kb:.0f} KB, over the {spec.max_kb} KB limit")
        if spec.min_kb and pf.size_kb < spec.min_kb:
            problems.append(f"is {pf.size_kb:.0f} KB, under the {spec.min_kb} KB minimum")
        if not pf.legible:
            problems.append("may be hard to read after compressing")
        out += [_finding("file_spec", "file_spec", doc_type, "medium", p, msg.file_spec(doc_type, p)) for p in problems]
    return out


def image_quality(quality_by_doc: dict[str, dict]) -> list[Finding]:
    """`quality_by_doc` maps document type to extraction's Quality (too_blurry, too_dark)."""
    out = []
    for doc_type, q in quality_by_doc.items():
        for flag, word in (("too_blurry", "blurry"), ("too_dark", "too dark")):
            if q.get(flag):
                out.append(_finding("image_quality", "quality", doc_type, "medium", word, msg.quality(doc_type, word)))
    return out


def date_validity(docs: list[ExtractedDocument], today: date | None = None) -> list[Finding]:
    today = today or date.today()
    out = []
    for d in docs:
        if d.document_type not in ("income", "community"):
            continue
        until = d.fields.get("valid_until")
        expiry = norm_date(until.value) if until else None
        if expiry and expiry < today:
            out.append(_finding("date_validity", "validity", "valid_until", "high", f"expired on {expiry.isoformat()}",
                                msg.expired(d.document_type, expiry)))
        raw = d.fields.get("issue_date")
        issued = norm_date(raw.value) if raw else None
        if issued is None:
            out.append(_finding("date_validity", "validity", "issue_date", "low", "issue date not found",
                                msg.validity(d.document_type, "could not be read")))
        elif issued > today:
            out.append(_finding("date_validity", "validity", "issue_date", "low", "issue date in the future",
                                msg.validity(d.document_type, "is in the future")))
    return out
