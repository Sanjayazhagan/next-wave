from contracts.documents import ExtractedDocument
from contracts.profile import Profile, ProfileField
from modules.extraction.confidence import score
from modules.extraction.merge import merge_profile
from modules.extraction.ocr import OcrLine


def _ln(text, y):
    return OcrLine(text=text, box=(10, y, 300, 20), words=[])


LINES = [_ln("This is to certify that S. SATYAJIT", 100), _ln("son of K. Subramanian residing at", 130),
         _ln("Annual income Rs. 2,50,000/-", 160)]


def test_agreeing_valid_value_scores_high():
    conf, bbox = score("full_name", "S. SATYAJIT", "S. SATYAJIT", LINES)
    assert conf >= 0.95 and bbox == [10.0, 100.0, 300.0, 20.0]


def test_value_not_on_page_scores_low():
    conf, _ = score("full_name", "Ramesh Kumar", "Ramesh Kumar", LINES)
    assert conf < 0.8


def test_value_wrapping_two_lines_matches():
    lines = [_ln("Name: SATYAJIT SUBRAMANIAN", 100), _ln("KRISHNAMOORTHY", 130)]
    conf, _ = score("full_name", "SATYAJIT SUBRAMANIAN KRISHNAMOORTHY", None, lines)
    assert conf >= 0.95


def test_null_value_scores_zero():
    assert score("full_name", None, None, LINES) == (0.0, None)


def _doc(doc_type, **fields):
    return ExtractedDocument(document_type=doc_type, file_ref="f", fields={
        k: ProfileField(value=v, source_document=doc_type, confidence=c) for k, (v, c) in fields.items()})


def test_merge_keeps_highest_confidence_and_user_answers():
    prior = Profile(fields={"community": ProfileField(value="BC / MBC", source_document="user_answer", confidence=1.0)})
    p = merge_profile([_doc("community", full_name=("S Satyajit", 0.7), community=("MBC", 0.99)),
                       _doc("marksheet", full_name=("S. Satyajit", 0.95))], prior)
    assert p.fields["full_name"].source_document == "marksheet"
    assert p.fields["community"].value == "BC / MBC"
