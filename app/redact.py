"""Keeps personal data out of LLM prompts, logs and the audit trail."""
import re
from collections.abc import Mapping

PATTERNS = [
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "<aadhaar>"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "<pan>"),
    (re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "<ifsc>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)"), "<phone>"),
    (re.compile(r"(?<!\d)\d{9,18}(?!\d)"), "<number>"),
]
MIN_KNOWN_VALUE_LENGTH = 3
MIN_MASKED_DIGITS = 9  # Longer than any date or income figure on a form.


def redact(text: str, known: Mapping[str, str] | None = None) -> str:
    """Swap known profile values for their field names, then mask ID patterns."""
    values = sorted((known or {}).items(), key=lambda item: -len(item[1]))
    for field, value in values:
        if len(value) >= MIN_KNOWN_VALUE_LENGTH:
            pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
            text = re.sub(pattern, f"<field:{field}>", text, flags=re.IGNORECASE)
    for pattern, label in PATTERNS:
        text = pattern.sub(label, text)
    return text


def mask_for_display(field: str, value: str) -> str:
    """Show the user only the last 4 digits of a sensitive number."""
    digits = re.sub(r"\D", "", value)
    named_sensitive = any(word in field.lower() for word in ("aadhaar", "bank", "account"))
    if named_sensitive or len(digits) >= MIN_MASKED_DIGITS:
        return f"XXXX{digits[-4:]}" if digits else "XXXX"
    return value
