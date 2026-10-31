"""Word files become PDFs in code, and never quietly lose what they hold."""
import io

import pypdfium2
import pytest
from docx import Document
from docx.document import Document as WordDocument
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from PIL import Image

import app.word
from app.documents import JPEG, PDF, DocumentError, fit_document
from app.word import DOCX, is_docx, word_to_pdf
from contracts.browser import FileRules

CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def saved(document: WordDocument) -> bytes:
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def picture() -> io.BytesIO:
    output = io.BytesIO()
    Image.new("RGB", (200, 200), "navy").save(output, "PNG")
    output.seek(0)
    return output


def certificate() -> WordDocument:
    document = Document()
    document.add_paragraph("Income Certificate", style="Title")
    document.add_paragraph("Family income is Rs. 120000.")
    return document


def text_of(pdf: bytes) -> str:
    document = pypdfium2.PdfDocument(pdf)
    try:
        pages = [document[index].get_textpage().get_text_bounded() for index in range(len(document))]
    finally:
        document.close()
    return " ".join(" ".join(pages).split())


def image_count(pdf: bytes) -> int:
    document = pypdfium2.PdfDocument(pdf)
    try:
        objects = document[0].get_objects(filter=[pypdfium2.raw.FPDF_PAGEOBJ_IMAGE])
        return len(list(objects))
    finally:
        document.close()


def test_recognises_word_files() -> None:
    assert is_docx(saved(certificate()))
    assert not is_docx(b"PK not really a zip")
    assert not is_docx(b"%PDF-1.4")


def test_words_tables_headers_and_footers_are_kept() -> None:
    document = certificate()
    document.sections[0].header.paragraphs[0].text = "Revenue Department"
    document.sections[0].footer.paragraphs[0].text = "Reference TN-4821"
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Demo Student"
    table.cell(1, 0).merge(table.cell(1, 1)).text = "Annual income"
    document.add_paragraph("First point", style="List Bullet")

    text = text_of(word_to_pdf(saved(document)))
    for words in (
        "Revenue Department", "Income Certificate", "Rs. 120000", "Demo Student",
        "Annual income", "First point", "Reference TN-4821",
    ):
        assert words in text


def test_pictures_are_kept() -> None:
    document = certificate()
    document.add_picture(picture())
    assert image_count(word_to_pdf(saved(document))) == 1


def test_a_seal_floating_over_the_page_is_kept() -> None:
    document = certificate()
    document.add_picture(picture())
    inline = next(document.element.body.iter(qn("wp:inline")))
    inline.tag = qn("wp:anchor")
    assert image_count(word_to_pdf(saved(document))) == 1


def test_a_picture_in_a_table_is_kept() -> None:
    document = certificate()
    cell = document.add_table(rows=1, cols=1).cell(0, 0)
    cell.paragraphs[0].add_run().add_picture(picture())
    assert image_count(word_to_pdf(saved(document))) == 1


def test_a_chart_is_refused_rather_than_dropped() -> None:
    document = certificate()
    run = document.add_paragraph().add_run()
    run._r.append(parse_xml(
        f'<w:drawing {nsdecls("w", "a")}><a:graphic><a:graphicData uri="{CHART}"/>'
        "</a:graphic></w:drawing>"
    ))
    with pytest.raises(DocumentError, match="chart"):
        word_to_pdf(saved(document))


def test_a_language_no_font_can_print_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    latin_only = app.word._font_files()[:1]
    latin_only = tuple(
        (path, frozenset(c for c in characters if c < 0x250)) for path, characters in latin_only
    )
    monkeypatch.setattr(app.word, "_font_files", lambda: latin_only)
    document = certificate()
    document.add_paragraph("வருமான சான்றிதழ்")
    with pytest.raises(DocumentError, match="font"):
        word_to_pdf(saved(document))


def test_a_huge_unzipped_file_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.word, "MAX_UNZIPPED_BYTES", 10)
    with pytest.raises(DocumentError, match="too large"):
        word_to_pdf(saved(certificate()))


async def test_a_form_wanting_a_pdf_gets_one() -> None:
    data, mime_type = await fit_document(saved(certificate()), DOCX, FileRules(formats=[PDF]))
    assert mime_type == PDF
    assert "Income Certificate" in text_of(data)


async def test_a_form_wanting_a_photo_gets_one() -> None:
    data, mime_type = await fit_document(
        saved(certificate()), DOCX, FileRules(formats=[JPEG], max_bytes=200_000)
    )
    assert mime_type == JPEG
    assert data.startswith(b"\xff\xd8")


async def test_a_form_taking_word_files_gets_the_original() -> None:
    source = saved(certificate())
    assert await fit_document(source, DOCX, FileRules(formats=[DOCX])) == (source, DOCX)


async def test_old_word_files_are_refused() -> None:
    old_format = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600
    with pytest.raises(DocumentError):
        await fit_document(old_format, "application/msword", FileRules(formats=[PDF]))


async def test_iphone_photos_are_converted() -> None:
    output = io.BytesIO()
    Image.effect_noise((600, 400), 40).convert("RGB").save(output, "HEIF")
    data, mime_type = await fit_document(
        output.getvalue(), "image/heic", FileRules(formats=[JPEG])
    )
    assert mime_type == JPEG
    assert Image.open(io.BytesIO(data)).size == (600, 400)

