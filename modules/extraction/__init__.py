"""M1 document extraction, loaded by core through app/plugins.py.

    extract(images: list[DocumentImage]) -> ExtractionResult

Each uploaded image (or PDF) is treated as one document. Pages are classified,
masked, read by the vision model and checked against Tesseract OCR.
"""
from __future__ import annotations

import asyncio
import logging

from contracts.documents import DocumentImage, ExtractedDocument, ExtractionResult

from . import preprocess
from .merge import merge_profile, to_contract
from .pipeline import extract_pages

log = logging.getLogger(__name__)

__all__ = ["extract", "extract_sync", "merge_profile"]


def extract_sync(images: list[DocumentImage]) -> ExtractionResult:
    documents: list[ExtractedDocument] = []
    for image in images:
        try:
            pages = preprocess.load_pages(image.data, image.mime_type)
            result = extract_pages(pages)
        except Exception as exc:
            # One unreadable upload must not stop the run; the questions cover the gap.
            log.warning("Extraction failed for one document: %s", type(exc).__name__)
            continue
        documents.append(to_contract(result, image.file_ref))
    return ExtractionResult(profile=merge_profile(documents), documents=documents)


async def extract(images: list[DocumentImage]) -> ExtractionResult:
    """Core's plug-in entry point. OCR and image work run off the event loop."""
    return await asyncio.to_thread(extract_sync, images)
