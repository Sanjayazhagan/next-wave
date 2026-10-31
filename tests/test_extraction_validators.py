from datetime import date

import pytest

from modules.extraction.validators import check

TODAY = date(2026, 10, 31)


@pytest.mark.parametrize("field,value,ok", [
    ("full_name", "S. Satyajit", True), ("full_name", "S", False), ("full_name", "R2D2", False),
    ("father_name", "K Subramanian", True),
    ("date_of_birth", "2005-08-15", True), ("date_of_birth", "2020-01-01", False), ("date_of_birth", date(1950, 1, 1), False),
    ("marks_percent", 87.5, True), ("marks_percent", 101, False), ("marks_percent", "abc", False),
    ("annual_income", 250000, True), ("annual_income", "Rs. 2,50,000/-", True),
    ("annual_income", -5, False),
    ("community", "MBC", True), ("community", "Most Backward Class", True), ("community", "Martian", False),
    ("issue_date", "2025-06-01", True), ("issue_date", "2027-01-01", False), ("issue_date", "1999-01-01", False),
    ("exam_year", 2025, True), ("exam_year", 1990, False),
    ("district", "Chennai", True), ("district", "", False), ("district", None, False),
])
def test_check(field, value, ok):
    assert check(field, value, today=TODAY) is ok
