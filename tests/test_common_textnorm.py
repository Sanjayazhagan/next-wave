from datetime import date

import pytest

from common.textnorm import norm_amount, norm_date, norm_text


def test_norm_text():
    assert norm_text("  S. SATYAJIT,  B.Tech/CSE - II ") == "s satyajit b tech/cse - ii"


@pytest.mark.parametrize("raw,expected", [
    ("Rs. 2,50,000/-", 250000), ("₹250000", 250000), ("2.5 lakh", 250000),
    ("Two Lakh Fifty Thousand", 250000), ("Rupees One Lakh Only", 100000), (72000, 72000), ("abc", None),
])
def test_norm_amount(raw, expected):
    assert norm_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("15/08/2005", date(2005, 8, 15)), ("15-08-2005", date(2005, 8, 15)), ("15.08.2005", date(2005, 8, 15)),
    ("2005-08-15", date(2005, 8, 15)), ("15 Aug 2005", date(2005, 8, 15)), ("31/02/2005", None), ("x", None),
])
def test_norm_date(raw, expected):
    assert norm_date(raw) == expected


from common.textnorm import norm_category  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("BC", "BC"), ("b.c.", "BC"), ("Most Backward Class", "MBC"), ("Backward Class", "BC"),
    ("Backward Class (Muslim)", "BCM"), ("Scheduled Caste", "SC"), ("Other Backward Classes", "OBC"),
    ("Martian", None), (None, None),
])
def test_norm_category(raw, expected):
    assert norm_category(raw) == expected
