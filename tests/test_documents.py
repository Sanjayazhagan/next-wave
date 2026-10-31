"""Every form has its own upload rules, so these cover many different ones."""
import io
from typing import Any

import pypdfium2
import pytest
from PIL import Image

from app.documents import (
    JPEG,
    PDF,
    PNG,
    DocumentError,
    combine,
    file_name,
    fit_document,
    parse_rules,
)
from app.planner import Planner
from contracts.browser import FileRules, PageNode, Snapshot

KB = 1000
MB = 1000 * KB


def photo(size: tuple[int, int] = (3000, 2200), kind: str = "JPEG") -> bytes:
    """Fine grain, which is what makes real phone photos so heavy."""
    image = Image.effect_noise(size, 60).convert("RGB")
    output = io.BytesIO()
    image.save(output, format=kind, quality=95)
    return output.getvalue()


def pdf(pages: int = 1) -> bytes:
    images = [Image.effect_noise((1700, 2200), 60).convert("RGB") for _ in range(pages)]
    output = io.BytesIO()
    images[0].save(output, "PDF", save_all=True, append_images=images[1:], quality=95)
    return output.getvalue()


def page_count(data: bytes) -> int:
    document = pypdfium2.PdfDocument(data)
    try:
        return len(document)
    finally:
        document.close()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Upload marksheet", FileRules()),
        ("Max 200 KB", FileRules(max_bytes=200 * KB)),
        ("Size should not exceed 2MB", FileRules(max_bytes=2 * MB)),
        ("not more than 1.5 MB", FileRules(max_bytes=1_500_000)),
        ("up to 500 kilobytes", FileRules(max_bytes=500 * KB)),
        ("20 KB to 50 KB", FileRules(min_bytes=20 * 1024, max_bytes=50 * KB)),
        ("20-50 KB", FileRules(min_bytes=20 * 1024, max_bytes=50 * KB)),
        ("between 500 KB and 1 MB", FileRules(min_bytes=500 * 1024, max_bytes=MB)),
        ("Minimum 10 KB and maximum 2 MB", FileRules(min_bytes=10 * 1024, max_bytes=2 * MB)),
        ("Max 1 MB, at least 10 KB", FileRules(min_bytes=10 * 1024, max_bytes=MB)),
        ("not less than 20KB", FileRules(min_bytes=20 * 1024)),
        ("PDF only", FileRules(formats=[PDF])),
        ("JPG or PNG, up to 500 KB", FileRules(formats=[JPEG, PNG], max_bytes=500 * KB)),
        ("JPEG/JPG", FileRules(formats=[JPEG])),
        ("Photo 200 x 230 pixels", FileRules(width=200, height=230)),
        ("signature 140×60 px", FileRules(width=140, height=60)),
    ],
)
def test_rules_are_read_from_the_forms_own_words(text: str, expected: FileRules) -> None:
    assert parse_rules(text) == expected


@pytest.mark.parametrize(
    ("accept", "formats"),
    [
        ("", []),
        ("*/*", []),
        (".pdf", [PDF]),
        ("application/pdf", [PDF]),
        (".jpg,.jpeg", [JPEG]),
        ("image/png, image/jpeg", [PNG, JPEG]),
        ("image/*", [JPEG, PNG]),
        (".doc", [".doc"]),
    ],
)
def test_accept_lists(accept: str, formats: list[str]) -> None:
    assert parse_rules("", accept).formats == formats


def test_accept_list_beats_the_wording() -> None:
    assert parse_rules("Upload your PDF", ".png").formats == [PNG]


async def test_a_form_stating_nothing_gets_the_file_untouched() -> None:
    data = b"anything at all"
    assert await fit_document(data, "text/plain", FileRules()) == (data, "text/plain")


async def test_a_file_that_already_fits_is_not_recompressed() -> None:
    data = photo((400, 300))
    rules = FileRules(formats=[JPEG, PDF], max_bytes=10 * MB)
    assert await fit_document(data, JPEG, rules) == (data, JPEG)


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        (FileRules(max_bytes=5 * MB), JPEG),
        (FileRules(max_bytes=200 * KB), JPEG),
        (FileRules(min_bytes=20 * 1024, max_bytes=50 * KB), JPEG),
        (FileRules(formats=[JPEG], max_bytes=30 * KB), JPEG),
        (FileRules(formats=[PDF], max_bytes=MB), PDF),
        (FileRules(formats=[PDF], max_bytes=100 * KB), PDF),
        (FileRules(formats=[PNG], max_bytes=2 * MB), PNG),
        (FileRules(formats=[PDF, PNG]), PNG),
    ],
)
async def test_one_photo_meets_many_different_forms(rules: FileRules, expected: str) -> None:
    data, mime_type = await fit_document(photo(), JPEG, rules)
    assert mime_type == expected
    assert data.startswith(b"%PDF-") == (expected == PDF)
    if rules.max_bytes:
        assert len(data) <= rules.max_bytes
    if rules.min_bytes:
        assert len(data) >= rules.min_bytes


async def test_exact_pixel_size() -> None:
    data, mime_type = await fit_document(photo(), JPEG, FileRules(width=200, height=230))
    assert mime_type == JPEG
    assert Image.open(io.BytesIO(data)).size == (200, 230)


async def test_a_png_or_webp_photo_can_become_what_the_form_wants() -> None:
    for source in ("PNG", "WEBP"):
        data, mime_type = await fit_document(
            photo((500, 400), source), "ignored/label", FileRules(formats=[JPEG])
        )
        assert mime_type == JPEG
        assert data.startswith(b"\xff\xd8")


async def test_a_pdf_can_become_a_photo() -> None:
    data, mime_type = await fit_document(pdf(), PDF, FileRules(formats=[JPEG], max_bytes=300 * KB))
    assert mime_type == JPEG
    assert data.startswith(b"\xff\xd8")
    assert len(data) <= 300 * KB


async def test_a_large_pdf_shrinks_and_keeps_all_its_pages() -> None:
    source = pdf(3)
    assert len(source) > MB
    data, mime_type = await fit_document(source, PDF, FileRules(formats=[PDF], max_bytes=MB))
    assert mime_type == PDF
    assert len(data) <= MB
    assert page_count(data) == 3


async def test_several_pages_are_never_cut_down_to_one_image() -> None:
    with pytest.raises(DocumentError):
        await fit_document(pdf(2), PDF, FileRules(formats=[JPEG]))


async def test_wrong_label_on_a_file_does_not_fool_it() -> None:
    data, mime_type = await fit_document(photo((400, 300)), PDF, FileRules(formats=[JPEG]))
    assert mime_type == JPEG
    assert data.startswith(b"\xff\xd8")


@pytest.mark.parametrize(
    ("data", "rules"),
    [
        (b"not a document", FileRules(formats=[PDF])),
        (b"x" * 2000, FileRules(max_bytes=1000)),
        (b"%PDF-1.4 broken", FileRules(max_bytes=5)),
        (photo((400, 300)), FileRules(formats=[".doc"])),
        (photo((400, 300)), FileRules(min_bytes=50 * MB)),
    ],
)
async def test_a_form_that_cannot_be_met_is_an_error(data: bytes, rules: FileRules) -> None:
    with pytest.raises(DocumentError):
        await fit_document(data, JPEG, rules)


def test_combine_keeps_the_tightest_sizes() -> None:
    rules = combine(
        FileRules(max_bytes=5 * MB, min_bytes=10), None, FileRules(max_bytes=MB, min_bytes=20)
    )
    assert (rules.max_bytes, rules.min_bytes) == (MB, 20)


def test_combine_keeps_the_formats_all_sources_allow() -> None:
    rules = combine(FileRules(formats=[JPEG, PNG]), FileRules(formats=[PDF, JPEG]))
    assert rules.formats == [JPEG]


def test_on_a_clash_the_form_beats_an_older_saved_rule() -> None:
    assert combine(FileRules(formats=[PDF]), FileRules(formats=[JPEG])).formats == [PDF]


@pytest.mark.parametrize(
    ("document", "mime_type", "expected"),
    [
        ("marksheet", PDF, "marksheet.pdf"),
        ("income certificate", JPEG, "income_certificate.jpg"),
        ("", PNG, "document.png"),
    ],
)
def test_file_names(document: str, mime_type: str, expected: str) -> None:
    assert file_name(document, mime_type) == expected


class Reply:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.user = ""

    async def complete_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        self.user = user
        return self.reply


PAGE = (
    "Photo: JPG, 20 KB to 50 KB. Certificate: PDF, maximum 1 MB. "
    "Welcome Priya Sharma, please upload both."
)
UPLOADS = Snapshot(
    url="https://portal.example/form",
    nodes=[
        PageNode(ref="a", role="file", name="Photo"),
        PageNode(ref="b", role="file", name="Certificate"),
    ],
    page_text=PAGE,
)


async def plan(rule_text: str) -> tuple[Reply, FileRules | None]:
    llm = Reply({"action": "upload", "ref": "b", "document": "cert", "rule_text": rule_text})
    step = await Planner(llm, "submit").next_step(
        "goal", UPLOADS, {"full_name": "Priya Sharma"}, ["cert"], []
    )
    return llm, step.file_rules


async def test_rules_quoted_from_the_page_are_used() -> None:
    _, rules = await plan("PDF, maximum 1 MB")
    assert rules == FileRules(formats=[PDF], max_bytes=MB)


async def test_a_limit_the_model_made_up_is_ignored() -> None:
    _, rules = await plan("PDF, maximum 10 KB")
    assert rules is None


async def test_page_text_reaches_the_model_only_masked() -> None:
    llm, _ = await plan("")
    assert "PDF, maximum 1 MB" in llm.user
    assert "Priya" not in llm.user


async def test_pages_without_an_upload_send_no_page_text() -> None:
    llm = Reply({"action": "wait"})
    snapshot = Snapshot(
        url="https://portal.example/form",
        nodes=[PageNode(ref="a", role="button", name="Next")],
        page_text="Applicant details shown here",
    )
    await Planner(llm, "submit").next_step("goal", snapshot, {}, [], [])
    assert "Applicant details" not in llm.user
