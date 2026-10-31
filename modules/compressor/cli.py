"""python -m modules.compressor.cli <file> --portal <id> --doc-type marksheet [--out out.pdf]"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import prepare_for_portal


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit a document file to a portal's upload limits")
    ap.add_argument("file", type=Path)
    ap.add_argument("--portal", required=True)
    ap.add_argument("--doc-type", required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    t0 = time.perf_counter()
    result = prepare_for_portal(a.file.read_bytes(), a.portal, a.doc_type)
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[result.info.mime]
    out = a.out or a.file.with_name(f"{a.file.stem}_prepared{ext}")
    out.write_bytes(result.data)
    info = result.info.model_copy(update={"path": str(out)})
    print(info.model_dump_json(indent=2))
    print(f"took {time.perf_counter() - t0:.2f}s")


if __name__ == "__main__":
    main()
