"""Plausibility checks per field. Used as 40% of the confidence score."""
from __future__ import annotations

import re
from datetime import date

from common.textnorm import norm_amount, norm_category, norm_date

_NAME = re.compile(r"^[A-Za-z][A-Za-z .]{1,59}$")


def _age(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def check(field: str, value: object, today: date | None = None) -> bool:
    """True when `value` is plausible for `field`. Fields without a rule pass if non-empty."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    today = today or date.today()
    if field in ("full_name", "father_name", "mother_name"):
        s = str(value).strip()
        return 2 <= len(s) <= 60 and bool(_NAME.match(s))
    if field == "date_of_birth":
        d = norm_date(value) if not isinstance(value, date) else value
        return d is not None and 14 <= _age(d, today) <= 60
    if field == "marks_percent":
        try:
            return 0 <= float(value) <= 100
        except (TypeError, ValueError):
            return False
    if field == "annual_income":
        n = norm_amount(value) if not isinstance(value, int) else value
        return n is not None and 0 <= n <= 100_000_000
    if field == "community":
        return norm_category(str(value)) is not None
    if field == "issue_date":
        d = norm_date(value) if not isinstance(value, date) else value
        return d is not None and date(2000, 1, 1) < d <= today
    if field == "exam_year":
        try:
            return 2000 <= int(value) <= today.year
        except (TypeError, ValueError):
            return False
    return True
