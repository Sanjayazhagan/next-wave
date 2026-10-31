"""One English fix sentence per check. Core translates them and can add Confirm / Upload buttons."""
from __future__ import annotations

DOC_NAMES = {"marksheet": "marksheet", "income": "income certificate", "community": "community certificate"}
FIELD_NAMES = {"full_name": "name", "father_name": "father's name", "date_of_birth": "date of birth",
               "community": "community", "annual_income": "family income"}


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


def missing_doc(d: str, name: str) -> str:
    return f"{name} needs your {doc(d)}. Please upload a clear photo of it."


def file_spec(d: str, problem: str) -> str:
    return f"Your {doc(d)} file {problem}. Upload a clearer photo or a PDF."


def quality(d: str, problem: str) -> str:
    return f"The photo of your {doc(d)} is {problem}. Retake it in good light, flat and in focus."


def validity(d: str, problem: str) -> str:
    return f"The issue date on your {doc(d)} {problem}. Check the certificate or upload a newer one."
