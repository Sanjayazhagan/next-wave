"""Turn per-document reads into the shared contract types."""
from __future__ import annotations

from contracts.documents import ExtractedDocument
from contracts.profile import Profile, ProfileField

from .models import DocResult


def to_contract(doc: DocResult, file_ref: str) -> ExtractedDocument:
    """`file_ref` is core's id for the original upload, so core can still find the file."""
    return ExtractedDocument(
        document_type=doc.doc_type,
        file_ref=file_ref,
        fields={k: ProfileField(value=f.as_text(), source_document=doc.doc_type, confidence=f.confidence)
                for k, f in doc.fields.items()},
    )


def merge_profile(docs: list[ExtractedDocument], prior: Profile | None = None) -> Profile:
    """Per field keep the highest-confidence value. User answers and edits are never overwritten.

    Conflicting values between documents are left for the doctor to report.
    """
    merged = dict(prior.fields) if prior else {}
    for doc in docs:
        for key, field in doc.fields.items():
            cur = merged.get(key)
            if cur is None or (not cur.source_document.startswith("user_") and field.confidence > cur.confidence):
                merged[key] = field
    return Profile(fields=merged)
