"""Prompts for document reading (one call decides the type and reads the fields)."""

# Kept short on purpose: every call's text counts against Groq's per-minute token allowance.
SYSTEM = (
    "You read Indian certificates and marksheets (often Tamil and English). Return only values printed "
    "on the document, else null; never guess. Names exactly as printed, with initials. Dates YYYY-MM-DD. "
    "Income: integer rupees per year. valid_until: end of the printed 'validity period'. "
    "evidence: the exact printed text each value came from."
)

LAYOUT_HINTS = {
    "marksheet": "Marksheet: name near the top; institution in the header; percentage or total and maximum "
                 "marks (marks_total, marks_max) under the marks table; exam year in header or footer.",
    "income": "Income certificate: number and date at the top; 'certify that <name> son/daughter of "
              "<father>'; annual family income in figures.",
    "community": "Community certificate: caste (e.g. Nadar) goes in caste; community is the category: "
                 "Backward Class, Most Backward Class, Denotified Community, Scheduled Caste/Tribe, or "
                 "'Other Backward Class' for a central OBC certificate.",
}

DOC_TYPES = ("doc_type: marksheet, income (income certificate), community (caste/community certificate) or "
             "other. Fill only that type's fields; null for the rest.")

NAMES = {"marksheet": "marksheet", "income": "income certificate", "community": "community certificate"}


def extract_prompt(doc_type: str | None) -> str:
    """Prompt for one known type, or (None) for deciding the type and reading it in the same call."""
    if doc_type:
        return f"Extract the fields from this {NAMES[doc_type]}. {LAYOUT_HINTS[doc_type]}"
    return "Decide what this document is and extract its fields. " + DOC_TYPES + " " + " ".join(LAYOUT_HINTS.values())


def retry_prompt(doc_type: str, field: str) -> str:
    return (f"This is a zoomed crop of a {NAMES[doc_type]}. Read only the field '{field}'. "
            "Return null if it is not printed in this crop.")
