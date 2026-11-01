"""Turn per-document reads into the shared contract types."""
from __future__ import annotations

from common.fields import PROFILE_FIELDS
from contracts.documents import ExtractedDocument
from contracts.profile import Profile, ProfileField

from .models import DocResult

# An income certificate is often issued to a parent, so its name, father's name and date of birth
# may not be the student's (the doctor reports such certificates; see parent_held there).
INCOME_GIVES = {"annual_income", "district", "state"}


def to_contract(doc: DocResult, file_ref: str) -> ExtractedDocument:
    """`file_ref` is core's id for the original upload, so core can still find the file."""
    return ExtractedDocument(
        document_type=doc.doc_type,
        file_ref=file_ref,
        fields={k: ProfileField(value=f.as_text(k), source_document=doc.doc_type, confidence=f.confidence)
                for k, f in doc.fields.items()},
    )


def merge_profile(docs: list[ExtractedDocument], prior: Profile | None = None) -> Profile:
    """Per field keep the highest-confidence value. User answers and edits are never overwritten.

    Only core's profile field names (common.fields.PROFILE_FIELDS) are merged.

    Conflicting values between documents are left for the doctor to report.
    """
    merged = dict(prior.fields) if prior else {}
    for doc in docs:
        for key, field in doc.fields.items():
            if key not in PROFILE_FIELDS:   # certificate details stay on the document
                continue
            if doc.document_type == "income" and key not in INCOME_GIVES:
                continue   # often a parent's certificate: its names would be the parent's
            cur = merged.get(key)
            if cur is None or (not cur.source_document.startswith("user_") and field.confidence > cur.confidence):
                merged[key] = field
    return Profile(fields=merged)
