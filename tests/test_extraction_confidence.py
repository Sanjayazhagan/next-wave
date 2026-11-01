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


def _words_line(*pairs, y=100):
    from modules.extraction.ocr import OcrWord
    words = [OcrWord(t, c, (10 + 80 * i, y, 70, 20), (1, 1, 1)) for i, (t, c) in enumerate(pairs)]
    return OcrLine(text=" ".join(t for t, _ in pairs), box=(10, y, 400, 20), words=words)


def test_snap_to_print_fixes_a_one_letter_slip():
    from modules.extraction.confidence import snap_to_print
    lines = [_words_line(("certify", 95), ("that", 96), ("Shri.", 90), ("Satyajit", 93), ("son", 95))]
    assert snap_to_print("Sathyajit", lines) == "Satyajit"
    assert snap_to_print("SATHYAJIT S", lines) == "SATYAJIT S"


def test_snap_to_print_leaves_unsure_or_different_words():
    from modules.extraction.confidence import snap_to_print
    unsure = [_words_line(("Satyajit", 60))]
    assert snap_to_print("Sathyajit", unsure) == "Sathyajit"          # OCR not confident
    other = [_words_line(("Ramesh", 95))]
    assert snap_to_print("Sathyajit", other) == "Sathyajit"           # not a near match
    assert snap_to_print("K. Priya", [_words_line(("K.", 95), ("Priya", 95))]) == "K. Priya"


def test_snap_fixes_a_place_name():
    from modules.extraction.confidence import snap_to_print
    lines = [_words_line(("District", 95), (":", 90), ("Chengalpattu", 92))]
    assert snap_to_print("Chengalpatu", lines) == "Chengalpattu"


def test_a_parents_income_certificate_gives_income_not_names():
    docs = [_doc("community", full_name=("Satyajit", 1.0), father_name=("Solai Rajan", 1.0)),
            _doc("income", full_name=("Solairajan P", 1.0), father_name=("Patchaimal", 1.0),
                 annual_income=("144000", 0.98), district=("Chengalpattu", 1.0))]
    p = merge_profile(docs)
    assert p.fields["father_name"].value == "Solai Rajan"     # not the grandfather
    assert p.fields["full_name"].value == "Satyajit"
    assert p.fields["annual_income"].value == "144000" and p.fields["annual_income"].source_document == "income"
