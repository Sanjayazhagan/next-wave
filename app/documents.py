"""Fits a document to what one form asks for.

Forms differ, so no form's rules live here: they come from the form itself, as
FileRules, and this only reads them and meets them.
"""
import asyncio
import io
import re
from collections.abc import Sequence

import pypdfium2
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from app.word import DOCX, DocumentError, is_docx, word_to_pdf
from contracts.browser import FileRules

register_heif_opener()  # iPhones save photos as HEIC.

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"
EXTENSIONS = {PDF: "pdf", JPEG: "jpg", PNG: "png"}
FORMAT_WORDS = {"pdf": PDF, "jpg": JPEG, "jpeg": JPEG, "png": PNG}
ACCEPT_VALUES = {
    **{f".{word}": mime for word, mime in FORMAT_WORDS.items()},
    PDF: PDF, JPEG: JPEG, PNG: PNG, "image/jpg": JPEG, DOCX: DOCX, ".docx": DOCX,
}
MAX_PIXELS = 20_000_000  # Refuse images large enough to exhaust the server's memory.
MAX_PAGES = 20
PDF_SCALE = 150 / 72  # Renders pages at 150 dpi, which keeps text readable.
# Tried from best to worst, so a file loses only as much as its form demands.
SCALES = (1, 0.8, 0.6, 0.45, 0.33, 0.25, 0.18, 0.12, 0.08)
QUALITIES = (90, 75, 60, 45)

FORMAT = re.compile(r"\b(pdf|jpe?g|png)\b", re.IGNORECASE)
NUMBER = r"\d+(?:\.\d+)?"
UNIT = r"(kb|mb|kilobytes?|megabytes?)\b"
SIZE = re.compile(rf"({NUMBER})\s*{UNIT}", re.IGNORECASE)
SIZE_RANGE = re.compile(
    rf"({NUMBER})\s*(kb|mb)?\s*(?:-|–|to|and)\s*({NUMBER})\s*{UNIT}", re.IGNORECASE
)
MINIMUM = re.compile(
    r"\b(?:min(?:imum)?|at least|n(?:ot|o) less than"
    r"|(?<!not )(?<!no )(?:more than|greater than|above|over))\b[^\d]*$",
    re.IGNORECASE,
)
PIXELS = re.compile(r"(\d{2,4})\s*[x×*]\s*(\d{2,4})\s*(?:px|pixels?)\b", re.IGNORECASE)


def _to_bytes(value: str, unit: str, kilobyte: int) -> int:
    return int(float(value) * (kilobyte if unit[0].lower() == "k" else kilobyte**2))


# Forms mean 1000 or 1024 by "KB", so each limit takes the stricter reading.
def _as_maximum(value: str, unit: str) -> int:
    return _to_bytes(value, unit, 1000)


def _as_minimum(value: str, unit: str) -> int:
    return _to_bytes(value, unit, 1024)


def _accepted(accept: str) -> list[str]:
    """Read an HTML accept list. A value we cannot make stays, so it fails honestly."""
    formats: list[str] = []
    for item in accept.lower().split(","):
        item = item.strip()
        if item == "*/*":
            return []
        found = [JPEG, PNG] if item == "image/*" else [ACCEPT_VALUES.get(item, item)]
        formats += [mime for mime in found if mime and mime not in formats]
    return formats


def parse_rules(text: str, accept: str = "") -> FileRules:
    """Read rules from the form's own words, and its accept list when it has one."""
    rules = FileRules(
        formats=_accepted(accept)
        or list(dict.fromkeys(FORMAT_WORDS[word.lower()] for word in FORMAT.findall(text)))
    )
    if pixels := PIXELS.search(text):
        rules.width, rules.height = int(pixels[1]), int(pixels[2])
    if span := SIZE_RANGE.search(text):
        rules.min_bytes = _as_minimum(span[1], span[2] or span[4])
        rules.max_bytes = _as_maximum(span[3], span[4])
        return rules
    for size in SIZE.finditer(text):
        if MINIMUM.search(text[max(0, size.start() - 40) : size.start()]):
            rules.min_bytes = _as_minimum(size[1], size[2])
        else:
            limit = _as_maximum(size[1], size[2])
            rules.max_bytes = min(rules.max_bytes or limit, limit)
    return rules


def combine(*sources: FileRules | None) -> FileRules:
    """Apply every source at once. On a format clash, the earlier source wins."""
    result = FileRules()
    for rules in filter(None, sources):
        shared = [mime for mime in result.formats if mime in rules.formats]
        result.formats = shared or result.formats or list(rules.formats)
        result.width = result.width or rules.width
        result.height = result.height or rules.height
        if rules.max_bytes:
            result.max_bytes = min(result.max_bytes or rules.max_bytes, rules.max_bytes)
        if rules.min_bytes:
            result.min_bytes = max(result.min_bytes or 0, rules.min_bytes)
    return result


def file_name(document: str, mime_type: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", document)[:60] or "document"
    return f"{stem}.{EXTENSIONS.get(mime_type, mime_type.rsplit('/', 1)[-1])}"


def _kind(data: bytes) -> str | None:
    """The file's real type, since a name or a sender's label can be wrong."""
    if data.startswith(b"%PDF-"):
        return PDF
    if is_docx(data):
        return DOCX
    try:
        with Image.open(io.BytesIO(data)) as image:
            return Image.MIME.get(image.format or "")
    except (OSError, ValueError):
        return None


def _fits(data: bytes, kind: str | None, rules: FileRules) -> bool:
    if rules.formats and kind not in rules.formats:
        return False
    if rules.max_bytes and len(data) > rules.max_bytes:
        return False
    if rules.min_bytes and len(data) < rules.min_bytes:
        return False
    if rules.width and rules.height:
        if kind is None or not kind.startswith("image/"):
            return False
        with Image.open(io.BytesIO(data)) as image:
            return image.size == (rules.width, rules.height)
    return True


def _pdf_pages(data: bytes) -> list[Image.Image]:
    try:
        document = pypdfium2.PdfDocument(data)
    except pypdfium2.PdfiumError as exc:
        raise DocumentError("This PDF cannot be opened") from exc
    try:
        if len(document) > MAX_PAGES:
            raise DocumentError("This PDF has too many pages")
        pages = []
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()
            if width * height * PDF_SCALE**2 > MAX_PIXELS:
                raise DocumentError("This PDF has a page that is too large")
            pages.append(page.render(scale=PDF_SCALE).to_pil().convert("RGB"))
        return pages
    finally:
        document.close()


def _image_pages(data: bytes) -> list[Image.Image]:
    with Image.open(io.BytesIO(data)) as opened:
        if opened.width * opened.height > MAX_PIXELS:
            raise DocumentError("This image is too large")
        # Phone photos store their rotation separately, and converting would lose it.
        return [ImageOps.exif_transpose(opened).convert("RGB")]


def _encode(pages: Sequence[Image.Image], target: str, quality: int) -> bytes:
    output = io.BytesIO()
    first, rest = pages[0], list(pages[1:])
    if target == PDF:
        first.save(output, "PDF", save_all=True, append_images=rest, quality=quality, resolution=150)
    elif target == JPEG:
        first.save(output, "JPEG", quality=quality, optimize=True)
    else:
        first.save(output, "PNG", optimize=True)
    return output.getvalue()


def _scaled(page: Image.Image, scale: float) -> Image.Image:
    if scale == 1:
        return page
    size = (max(1, round(page.width * scale)), max(1, round(page.height * scale)))
    return page.resize(size, Image.Resampling.LANCZOS)


def _convert(pages: Sequence[Image.Image], target: str, rules: FileRules) -> bytes | None:
    """The best copy that meets the rules, or None if no copy does."""
    scales: Sequence[float] = SCALES
    if rules.width and rules.height:
        pages = [ImageOps.pad(pages[0], (rules.width, rules.height), color="white")]
        scales = (1,)
    for scale in scales:
        resized = [_scaled(page, scale) for page in pages]
        for quality in (QUALITIES[0],) if target == PNG else QUALITIES:
            data = _encode(resized, target, quality)
            if _fits(data, target, rules):
                return data
    return None


def _targets(kind: str, rules: FileRules) -> list[str]:
    order = (PDF, JPEG, PNG) if kind == PDF else (JPEG, PNG, PDF)
    return [mime for mime in order if not rules.formats or mime in rules.formats]


def _fit(data: bytes, mime_type: str, rules: FileRules) -> tuple[bytes, str]:
    kind = _kind(data)
    if _fits(data, kind, rules):
        return data, kind or mime_type
    if kind is None:
        raise DocumentError("This file is not a readable image, PDF or Word file")
    if kind == DOCX:
        data, kind = word_to_pdf(data), PDF
        if _fits(data, kind, rules):
            return data, kind
    targets = _targets(kind, rules)
    if not targets:
        raise DocumentError(f"We cannot make this form's format: {', '.join(rules.formats)}")
    pages = _pdf_pages(data) if kind == PDF else _image_pages(data)
    for target in targets:
        if len(pages) > 1 and target != PDF:
            continue  # One image cannot hold several pages, and dropping them would mislead.
        fitted = _convert(pages, target, rules)
        if fitted is not None:
            return fitted, target
    raise DocumentError("This file cannot meet the form's rules")


async def fit_document(data: bytes, mime_type: str, rules: FileRules) -> tuple[bytes, str]:
    """Return the file and its type, unchanged if it already meets the rules."""
    return await asyncio.to_thread(_fit, data, mime_type, rules)
