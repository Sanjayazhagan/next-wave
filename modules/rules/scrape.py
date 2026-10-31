"""Snapshot official scheme pages and guideline PDFs into schemes/raw/<scheme_id>/.

    uv run python -m modules.rules.scrape [scheme_id ...]

HTML pages are rendered with Playwright (myscheme.gov.in needs JavaScript); PDFs are
downloaded with httpx and their text extracted with pypdf. Each source gets a
.txt file and meta.json records {url, scraped_at, sha256}. One second between requests.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from datetime import date
from pathlib import Path

import httpx
import yaml

SCHEMES_DIR = Path(__file__).resolve().parent / "schemes"
RAW = SCHEMES_DIR / "raw"
UA = "Mozilla/5.0 (X11; Linux x86_64) GradientZero-research/0.1 (+Forge 26 buildathon)"


def load_sources() -> list[dict]:
    return yaml.safe_load((SCHEMES_DIR / "sources.yaml").read_text())


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", url.lower().split("://", 1)[-1]).strip("_")[:80]


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)


def _page_text(page) -> str:
    main = page.locator("main")
    return (main.first if main.count() else page.locator("body")).inner_text()


def scrape(scheme_ids: list[str] | None = None) -> None:
    from playwright.sync_api import sync_playwright

    sources = [s for s in load_sources() if not scheme_ids or s["scheme_id"] in scheme_ids]
    with sync_playwright() as p, httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=60) as http:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA)
        for scheme in sources:
            out = RAW / scheme["scheme_id"]
            out.mkdir(parents=True, exist_ok=True)
            meta = []
            for url in scheme["urls"]:
                name = _slug(url)
                try:
                    if url.lower().endswith(".pdf"):
                        r = http.get(url)
                        r.raise_for_status()
                        raw, text = r.content, _pdf_text(r.content)
                        (out / f"{name}.pdf").write_bytes(raw)
                    else:
                        page.goto(url, wait_until="networkidle", timeout=60000)
                        html = page.content()
                        raw, text = html.encode(), _page_text(page)
                        (out / f"{name}.html").write_text(html, encoding="utf-8")
                except Exception as exc:  # record the failure; never fill in text by hand
                    print(f"FAIL {scheme['scheme_id']} {url}: {type(exc).__name__}: {str(exc)[:120]}")
                    continue
                (out / f"{name}.txt").write_text(text, encoding="utf-8")
                meta.append({"url": url, "file": f"{name}.txt", "scraped_at": date.today().isoformat(),
                             "sha256": hashlib.sha256(raw).hexdigest(), "chars": len(text)})
                print(f"ok   {scheme['scheme_id']} {url} ({len(text)} chars)")
                time.sleep(1)
            (out / "meta.json").write_text(json.dumps(meta, indent=2))
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scheme_ids", nargs="*")
    scrape(ap.parse_args().scheme_ids or None)
