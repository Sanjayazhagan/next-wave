"""Turns a Word .docx into a PDF in pure Python, so the server needs no LibreOffice.

The copy keeps the words, tables and images, but not the exact layout. A file with
something this cannot carry is refused, because a certificate that silently lost its
content is worse than one the applicant has to send again.
"""
import io
import logging
import re
import zipfile
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from fontTools.ttLib import TTCollection, TTFont
from fpdf import FPDF
from fpdf.errors import FPDFException
from lxml import etree
from PIL import Image, UnidentifiedImageError

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FONT_FOLDERS = ("/usr/share/fonts", r"C:\Windows\Fonts")
FONT_FILE = re.compile(r"\.(ttf|otf|ttc)$", re.IGNORECASE)
FONT_VARIANT = re.compile(r"bold|italic|oblique|light|thin|black|mono|condensed", re.IGNORECASE)
PREFERRED_FONTS = ("dejavusans.", "arial.")
MAX_UNZIPPED_BYTES = 100_000_000  # A small .docx can unzip into something enormous.
MAX_IMAGE_PIXELS = 20_000_000
EMU_PER_MM = 36_000
PAGE_WIDTH_MM = 180
LINE_HEIGHT_MM = 6
BODY_SIZE = 11
HEADING_SIZES = {"Title": 18, "Heading1": 15, "Heading2": 13, "Heading3": 12}
ALIGNMENT = {"center": "C", "right": "R", "both": "J"}
PICTURE_DATA = "http://schemas.openxmlformats.org/drawingml/2006/picture"
DRAWING_SHAPE_DATA = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
GRAPHIC_DATA = "{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData"
BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
EXTENT = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
EMBED = qn("r:embed")
logging.getLogger("fontTools.subset").setLevel(logging.ERROR)  # Noisy about every font table.


class DocumentError(Exception):
    """A document could not be fitted. The message holds nothing from the file."""


def is_docx(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            return "word/document.xml" in package.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _walk(element: Any) -> Iterator[Any]:
    """Every node once. Word stores old-format copies of shapes in Fallback."""
    for child in element:
        if child.tag == FALLBACK:
            continue
        yield child
        yield from _walk(child)


def _text_of(element: Any) -> str:
    parts = []
    for node in _walk(element):
        if node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("    ")
        elif node.tag == qn("w:br"):
            parts.append("\n")
    return "".join(parts)


def _images_of(element: Any, part: Any) -> list[tuple[bytes, float | None]]:
    """Each picture and its width in mm, refusing anything that is not a picture."""
    images = []
    width = None  # Word states a picture's size just before the picture.
    for node in _walk(element):
        if node.tag == GRAPHIC_DATA and node.get("uri") not in (PICTURE_DATA, DRAWING_SHAPE_DATA):
            raise DocumentError("This Word file has a chart or diagram we cannot copy")
        if node.tag == qn("w:object"):
            raise DocumentError("This Word file has an embedded object we cannot copy")
        if node.tag == EXTENT:
            width = int(node.get("cx", 0)) / EMU_PER_MM
        if node.tag == BLIP and node.get(EMBED):
            images.append((part.related_parts[node.get(EMBED)].blob, width))
    return images


def _blocks(root: Any) -> Iterator[Any]:
    """Paragraphs and tables in reading order, looking inside content controls."""
    for child in root:
        if child.tag in (qn("w:p"), qn("w:tbl")):
            yield child
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _blocks(content)


def _parts(document: Any) -> list[tuple[Any, Any]]:
    """The header, body and footer, each with the package part holding its pictures."""
    first = document.sections[0]
    return [
        (first.header._element, first.header.part),
        (document.element.body, document.part),
        (first.footer._element, first.footer.part),
    ]


@lru_cache(maxsize=1)
def _font_files() -> tuple[tuple[Path, frozenset[int]], ...]:
    """Each regular font on this machine and the characters it can print."""
    paths = [
        path
        for folder in FONT_FOLDERS
        if Path(folder).is_dir()
        for path in Path(folder).rglob("*")
        if FONT_FILE.search(path.name) and not FONT_VARIANT.search(path.name)
    ]
    paths.sort(key=lambda path: (not path.name.lower().startswith(PREFERRED_FONTS), path.name))
    found = []
    for path in paths:
        try:
            font = (
                TTCollection(path, lazy=True).fonts[0]
                if path.suffix.lower() == ".ttc"
                else TTFont(path, lazy=True)
            )
            found.append((path, frozenset(font.getBestCmap())))
            font.close()
        except Exception:  # A broken system font must not stop the conversion.
            continue
    return tuple(found)


def _fonts_for(text: str) -> list[Path]:
    """The fewest fonts covering this text. Refuses, rather than print blank boxes."""
    needed = {ord(character) for character in text if not character.isspace()}
    chosen: list[Path] = []
    fonts = _font_files()
    if fonts:
        chosen.append(fonts[0][0])
        needed -= fonts[0][1]
    for path, characters in fonts:
        if needed & characters:
            chosen.append(path)
            needed -= characters
    needed -= {0x200c, 0x200d, 0xfeff}  # Invisible joiners, which print nothing.
    if needed or not chosen:
        raise DocumentError("No font on this server can print this Word file's language")
    return chosen


def _new_pdf(text: str) -> FPDF:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(15, 15)
    pdf.add_page()
    families = []
    for index, path in enumerate(_fonts_for(text)):
        family = f"font{index}"
        pdf.add_font(family, fname=str(path), collection_font_number=0)
        families.append(family)
    pdf.set_font(families[0], size=BODY_SIZE)
    pdf.set_fallback_fonts(families[1:], exact_match=False)
    pdf.set_text_shaping(True)  # Tamil, Hindi and others are unreadable without this.
    return pdf


def _picture(pdf: FPDF, data: bytes, width: float | None) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise DocumentError("This Word file has an image that is too large")
            picture = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentError("This Word file has an image we cannot read") from exc
    pdf.image(picture, w=min(width or PAGE_WIDTH_MM, PAGE_WIDTH_MM), x=pdf.l_margin)
    pdf.ln(2)


def _pictures(pdf: FPDF, element: Any, part: Any) -> None:
    for data, width in _images_of(element, part):
        _picture(pdf, data, width)


def _paragraph(pdf: FPDF, element: Any, part: Any) -> None:
    text = _text_of(element).strip()
    if text:
        bullet = "• " if element.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None else ""
        alignment = element.find(f"{qn('w:pPr')}/{qn('w:jc')}")
        align = ALIGNMENT.get(alignment.get(qn("w:val")) if alignment is not None else "", "L")
        # A plain size change leaks into later lines once fallback fonts are in use.
        with pdf.local_context(font_size_pt=HEADING_SIZES.get(element.style or "", BODY_SIZE)):
            pdf.multi_cell(
                0, LINE_HEIGHT_MM, bullet + text, align=align, new_x="LMARGIN", new_y="NEXT"
            )
    _pictures(pdf, element, part)


def _table(pdf: FPDF, element: Any, part: Any) -> None:
    """Pictures in cells follow the table, because they would not stay aligned in it."""
    columns = max(sum(cell.grid_span for cell in row.tc_lst) for row in element.tr_lst)
    with pdf.table(
        col_widths=[1] * columns, first_row_as_headings=False, line_height=LINE_HEIGHT_MM
    ) as table:
        for source in element.tr_lst:
            row = table.row()
            for cell in source.tc_lst:
                row.cell(_text_of(cell).strip(), colspan=cell.grid_span)
            for _ in range(columns - sum(cell.grid_span for cell in source.tc_lst)):
                row.cell("")
    pdf.ln(3)
    _pictures(pdf, element, part)


def _unzipped_size(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return sum(entry.file_size for entry in package.infolist())


def word_to_pdf(data: bytes) -> bytes:
    if _unzipped_size(data) > MAX_UNZIPPED_BYTES:
        raise DocumentError("This Word file is too large")
    try:
        document = Document(io.BytesIO(data))
        parts = _parts(document)
        pdf = _new_pdf("".join(_text_of(root) for root, _ in parts))
        for root, part in parts:
            for block in _blocks(root):
                render = _paragraph if block.tag == qn("w:p") else _table
                render(pdf, block, part)
        return bytes(pdf.output())
    except (
        AttributeError, KeyError, TypeError, ValueError,
        FPDFException, etree.LxmlError, zipfile.BadZipFile,
    ) as exc:
        raise DocumentError("This Word file cannot be opened") from exc
