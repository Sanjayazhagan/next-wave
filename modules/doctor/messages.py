"""A readable heading and one English fix sentence per finding. localize.py translates them."""
from __future__ import annotations

DOC_NAMES = {"marksheet": "marksheet", "income": "income certificate", "community": "community certificate"}
FIELD_NAMES = {"full_name": "name", "father_name": "father's name", "mother_name": "mother's name",
               "date_of_birth": "date of birth", "community": "community", "annual_income": "family income",
               "gender": "gender", "state": "state", "course": "course", "marks_percentage": "marks percentage",
               "disability_percent": "disability percentage", "govt_school_6_to_12": "schooling (Class 6 to 12)",
               "issue_date": "issue date", "valid_until": "validity", "certificate_number": "certificate number"}


def label(field: str) -> str:
    """'valid_until' -> 'validity': never a raw field name in front of a user."""
    return FIELD_NAMES.get(field, field.replace("_", " "))


def heading(check: str, field: str | None, document: str | None) -> str:
    """The short heading core shows before a fix ("Income certificate", "Name")."""
    if document and check in ("file_spec", "image_quality", "date_validity", "authenticity"):
        return doc(document).capitalize()
    if check == "eligibility_recheck":
        return "Eligibility"
    if check == "required_docs":
        return "Missing document"
    return label(field).capitalize() if field else "Documents"


def doc(d: str) -> str:
    return DOC_NAMES.get(d, d.replace("_", " "))


def name_mismatch(field: str, a_doc: str, a: str, b_doc: str, b: str) -> str:
    what = FIELD_NAMES.get(field, field)
    return (f"Your {what} is '{a}' on the {doc(a_doc)} but '{b}' on the {doc(b_doc)}. If both are you, tap Confirm; "
            f"otherwise upload a document where the {what} matches.")


def field_mismatch(field: str, values: dict[str, str], winner: str | None) -> str:
    what = FIELD_NAMES.get(field, field.replace("_", " "))
    listed = "; ".join(f"'{v}' on the {doc(d)}" for d, v in values.items())
    tail = f" The portal will go by the {doc(winner)}." if winner else ""
    return f"Your {what} differs between documents: {listed}.{tail} Check which is right and upload a corrected document if needed."


def not_eligible(name: str, reason: str) -> str:
    return f"Based on your documents you don't qualify for {name}: {reason} Choose another scheme or correct the document."


def needs_info(name: str, fields: list[str]) -> str:
    return f"Your documents don't confirm {', '.join(fields)} for {name}. Upload a document that shows it, or confirm it."


def state_community(name: str) -> str:
    # Worded for machine translation: "central OBC" came back in Tamil as "important OBC".
    return (f"Your community certificate is an OBC certificate from the Government of India, but {name} needs a "
            f"community certificate from the Tamil Nadu government showing BC, MBC or DNC. Upload that certificate.")


def missing_doc(d: str, name: str) -> str:
    return f"{name} needs your {doc(d)}. Please upload a clear photo of it."


def file_spec(d: str, problem: str) -> str:
    return f"Your {doc(d)} file {problem}. Upload a clearer photo or a PDF."


def quality(d: str, problem: str) -> str:
    return f"The photo of your {doc(d)} is {problem}. Retake it in good light, flat and in focus."


def expired(d: str, until) -> str:
    return (f"Your {doc(d)} expired on {until.strftime('%d %b %Y')}. Portals reject expired certificates: "
            f"get a fresh one from TN e-District (an e-Sevai centre) and upload it.")


def tampered(d: str, problems: dict[str, tuple[str, str]]) -> str:
    what = " and ".join(problems)
    return (f"The QR code on your {doc(d)} doesn't match its printed {what}, so the document may have been edited. "
            f"Upload the original certificate downloaded from TN e-District.")


def qr_unreadable(d: str, number: str) -> str:
    return (f"I couldn't read the QR code on your {doc(d)} to verify it. Upload the original PDF from TN e-District, "
            f"or verify number {number} at tnedistrict.tn.gov.in.")


def qr_missing(d: str) -> str:
    return (f"Your {doc(d)} has an e-District number but no QR code; genuine e-District certificates carry one. "
            f"Upload the original certificate downloaded from TN e-District.")


def validity(d: str, problem: str) -> str:
    return f"The issue date on your {doc(d)} {problem}. Check the certificate or upload a newer one."
