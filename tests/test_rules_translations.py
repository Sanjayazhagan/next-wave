"""Every scheme question and button the rule engine can send has Tamil and Hindi in core's table."""
import pytest

from app.translations import translate_fixed
from modules.rules import ANSWERS, to_contract
from modules.rules.questions import QUESTIONS
from modules.rules.translations import HINDI, TAMIL


def _sent_texts() -> set[str]:
    texts = set()
    for question in QUESTIONS.values():
        sent = to_contract(question)
        texts.add(sent.text)
        texts.update(sent.choices.values())
    return texts - {"SC", "ST", "BC", "MBC", "OC"}   # category codes read the same in every language


@pytest.mark.parametrize("table", [TAMIL, HINDI], ids=["ta", "hi"])
def test_every_question_and_button_is_translated(table):
    missing = sorted(_sent_texts() - set(table))
    assert not missing, f"no translation for {missing}"


def test_core_shows_scheme_questions_in_tamil_and_hindi():
    gender = to_contract(QUESTIONS["gender"])
    assert translate_fixed(gender.text, "ta") == "உங்கள் பாலினம் என்ன?"
    assert translate_fixed(gender.text, "hi") == "आपका लिंग क्या है?"
    assert [translate_fixed(label, "ta") for label in gender.choices.values()] == ["பெண்", "ஆண்", "திருநங்கை / திருநம்பி"]


def test_button_labels_cannot_corrupt_other_messages():
    # Core translates by replacing known English inside a message, so no label may be a bare word
    # that also appears inside ordinary sentences.
    for label in (label for choices in ANSWERS.values() for label in choices.values()):
        assert label not in {"Yes", "No", "Other", "OK"}


def test_more_than_eight_lakh_fails_an_eight_lakh_ceiling():
    stored = next(v for v, label in ANSWERS["annual_income"].items() if label == "More than ₹8 lakh")
    assert int(stored) > 800000
