"""Portal upload limits and prepared files: compressor <-> core and doctor.

One JSON file per portal in contracts/portals/<portal_id>.json. Every limit
cites where it came from in `source_note`; limits are never guessed.
"""
from typing import Literal

from pydantic import BaseModel

FileType = Literal["jpg", "jpeg", "png", "pdf"]


class DocSpec(BaseModel):
    doc_type: str                           # "*" applies to every document on the portal
    accepted_types: list[FileType]
    max_kb: int
    min_kb: int | None = None
    max_px: tuple[int, int] | None = None   # (width, height)
    source_note: str | None = None          # where this limit came from


class PortalSpec(BaseModel):
    portal_id: str
    name: str
    documents: list[DocSpec]


class PreparedFile(BaseModel):
    path: str | None = None
    mime: str
    size_kb: float
    px: tuple[int, int] | None
    pages: int
    actions: list[str]                      # human-readable, shown in the web app
    legible: bool
    words_before: int | None
    words_after: int | None
