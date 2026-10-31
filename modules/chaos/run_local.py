"""Check chaos.js on test_form.html: every mode, three seeds.

    uv run python -m modules.chaos.run_local

For each run: load the form, inject chaos, fill every field BY `name` attribute,
open any <details>, close any popup, submit, and check the submitted values are
exactly what was filled. Also checks the same seed gives the same log.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = (HERE / "chaos.js").read_text()
FORM = (HERE / "test_form.html").as_uri()
MODES = ["rename", "rewrap", "move", "hide", "popup", "slow"]
SEEDS = [1, 7, 42]
VALUES = {"full_name": "S Satyajit", "father_name": "K Subramanian", "dob": "2005-08-15", "category": "MBC",
          "income": "240000", "course": "B.E. Computer Science", "institution": "Anna University",
          "mobile": "9876543210"}


def run_once(page, mode: str, seed: int) -> tuple[list, dict]:
    page.goto(FORM)
    page.evaluate(SCRIPT)
    page.evaluate(SCRIPT)  # re-evaluating must not reinstall anything
    log = page.evaluate("opts => window.__chaos(opts)", {"mode": mode, "seed": seed, "count": 3})
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    dialog = page.get_by_role("dialog")
    if dialog.count():
        dialog.get_by_role("button", name="Close").click()
    for name, value in VALUES.items():
        el = page.locator(f'[name="{name}"]')
        if el.evaluate("e => e.tagName") == "SELECT":
            el.select_option(value)
        else:
            el.fill(value)
    page.locator('[name="certificate"]').set_input_files(
        files=[{"name": "income.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 test"}])
    page.get_by_role("button", name="Submit").click()
    page.wait_for_function("document.getElementById('out').textContent.length > 0", timeout=15000)
    return log, json.loads(page.locator("#out").text_content())


def main() -> int:
    from playwright.sync_api import sync_playwright

    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for mode in MODES:
            for seed in SEEDS:
                log, out = run_once(page, mode, seed)
                again, _ = run_once(page, mode, seed)
                ms = out.pop("_ms")
                problems = []
                if {k: out.get(k) for k in VALUES} != VALUES or out.get("certificate") != "income.pdf":
                    problems.append(f"submitted values changed: {out}")
                if log != again:
                    problems.append("same seed gave a different log")
                if not log:
                    problems.append("no changes logged")
                if mode == "slow" and ms < 2000:
                    problems.append(f"slow mode delayed only {ms} ms")
                status = "FAIL" if problems else "ok"
                failures += bool(problems)
                print(f"{status:4} {mode:7} seed={seed:<3} changes={len(log)} {'; '.join(problems)}")
        browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
