"""python -m modules.extraction.cli fixtures/docs/a_marksheet.jpg [--type marksheet]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import extract_paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract fields from a document photo or PDF")
    ap.add_argument("paths", nargs="+", type=Path, help="pages of one document")
    ap.add_argument("--type", dest="doc_type", choices=["marksheet", "income", "community"])
    ap.add_argument("--id", dest="doc_id")
    ap.add_argument("--no-retry", action="store_true")
    a = ap.parse_args()
    print(extract_paths(a.paths, a.doc_type, a.doc_id, retry=False if a.no_retry else None).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
