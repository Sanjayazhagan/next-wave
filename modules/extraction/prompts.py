"""Prompts for document classification and field extraction."""

SYSTEM = (
    "You read Indian government and academic documents, often bilingual Tamil and English. "
    "Return only values printed on the document. If a field is not printed, return null. "
    "Never infer or guess. Copy names exactly as printed, including initials. Dates as YYYY-MM-DD. "
    "Income as an integer number of rupees per year. For each field also return `evidence`: "
    "the exact printed text you read it from."
)

LAYOUT_HINTS = {
    "marksheet": (
        "Marksheets: the student's name and register number are near the top; the institution or board "
        "is in the header; the course/programme and semester or year are under the header; the total, "
        "maximum marks and percentage or CGPA are at the bottom of the marks table; the exam month and "
        "year are in the header or footer. If no percentage is printed, return marks_total and marks_max."
    ),
    "income": (
        "Tamil Nadu income certificates (Revenue Department): the certificate number and date are at the "
        "top; the body says 'This is to certify that <name> son/daughter of <father>' followed by the "
        "address with taluk and district; the annual family income is written in figures and words in the "
        "body. Return the income in figures as an integer."
    ),
    "community": (
        "Tamil Nadu community certificates: the certificate number and date are at the top; the body names "
        "the person, their father, the village/taluk/district, and the community (caste) and the category "
        "it belongs to, such as Backward Class or Most Backward Class or Scheduled Caste. Return the category "
        "as printed (e.g. 'Most Backward Class')."
    ),
}

CLASSIFY = (
    "Which kind of document is this? marksheet (academic mark statement or grade card), "
    "income (income certificate), community (caste/community certificate), or other."
)


NAMES = {"marksheet": "marksheet", "income": "income certificate", "community": "community certificate"}


def extract_prompt(doc_type: str) -> str:
    return f"Extract the fields from this {NAMES[doc_type]}. {LAYOUT_HINTS[doc_type]}"


def retry_prompt(doc_type: str, field: str) -> str:
    return (f"This is a zoomed crop of a {NAMES[doc_type]}. Read only the field '{field}'. "
            "Return null if it is not printed in this crop.")
