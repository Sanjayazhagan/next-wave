from app.graph.nodes import field_label


def test_code_names_become_plain_words() -> None:
    assert field_label("full_name") == "Name"
    assert field_label("valid_until") == "Expiry date"
    assert field_label("some_new_field") == "Some new field"


def test_a_readable_heading_is_left_alone() -> None:
    assert field_label("Income certificate") == "Income certificate"
    assert field_label("Father's name") == "Father's name"
    assert field_label("வருமானச் சான்றிதழ்") == "வருமானச் சான்றிதழ்"
