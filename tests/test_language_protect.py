from modules.language.protect import mask, unmask


def test_round_trip_keeps_amount_date_and_scheme_name():
    text = "Post Matric Scholarship gives ₹2,50,000 by 31/12/2026"
    masked, originals = mask(text, keep=["Post Matric Scholarship"])
    assert "₹2,50,000" not in masked and "31/12/2026" not in masked and "Post Matric" not in masked
    assert originals == ["Post Matric Scholarship", "₹2,50,000", "31/12/2026"]
    # Simulate a translation that moved the tokens around and added spaces inside one.
    translated = "⟦1⟧ உதவித்தொகை ⟦ 0 ⟧ மூலம் ⟦2⟧ க்குள்"
    restored, missing = unmask(translated, originals)
    assert restored == "₹2,50,000 உதவித்தொகை Post Matric Scholarship மூலம் 31/12/2026 க்குள்"
    assert missing == []


def test_missing_token_is_reported():
    masked, originals = mask("Pay Rs. 500 and bring ID TN-5202310")
    restored, missing = unmask("Pay ⟦0⟧ only", originals)
    assert restored == "Pay Rs. 500 only" and missing == ["TN-5202310"]
