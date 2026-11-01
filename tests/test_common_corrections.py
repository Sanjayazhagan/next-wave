import pytest

from common.corrections import normalize, parse_draft_edit

FILLED = {"full_name": {"label": "Applicant name"}, "annual_income": {"label": "Annual family income"},
          "date_of_birth": {"label": "DOB"}, "father_name": {"label": "Parent / guardian name"},
          "district": {"label": "District"}}


@pytest.mark.parametrize("text,expected", [
    ("2 120000", ("annual_income", "120000")),
    ("2. 1,20,000", ("annual_income", "1,20,000")),
    ("3: 15/08/2005", ("date_of_birth", "15/08/2005")),
    ("income 2 lakh", ("annual_income", "2 lakh")),
    ("change my date of birth to 15-08-2005", ("date_of_birth", "15-08-2005")),
    ("father's name should be K Subramanian", ("father_name", "K Subramanian")),
    ("Parent / guardian name: K Subramanian", ("father_name", "K Subramanian")),
    ("name S Satyajit", ("full_name", "S Satyajit")),
    ("2.5 lakh", ("annual_income", "2.5 lakh")),
    ("district Chengalpattu", ("district", "Chengalpattu")),
    ("name is Isha R", ("full_name", "Isha R")), ("name Isha R", ("full_name", "Isha R")),
    ("9 hello", None), ("hello there", None), ("income", None),
])
def test_parse_draft_edit(text, expected):
    assert parse_draft_edit(text, FILLED) == expected


@pytest.mark.parametrize("field,raw,expected", [
    ("annual_income", "2 lakh", "200000"), ("annual_income", "Rs. 1,44,000/-", "144000"),
    ("annual_income", "lots", None),
    ("date_of_birth", "15/08/2005", "15-08-2005"), ("date_of_birth", "2005-08-15", "15-08-2005"),
    ("date_of_birth", "31/02/2005", None), ("date_of_birth", "15/08/2030", None),
    ("full_name", "Thiru S Satyajit", "S Satyajit"), ("full_name", "Satyajit 123", None),
    ("marks_percentage", "87.5%", "87.5"), ("marks_percentage", "120", None),
    ("community", "Most Backward Class", "MBC"), ("community", "martian", None),
    ("gender", "girl", "Female"), ("district", "Chengalpattu", "Chengalpattu"),
])
def test_normalize(field, raw, expected):
    assert normalize(field, raw) == expected
