"""chaos.js on the local test form. Skipped when Playwright's Chromium isn't installed."""
import pytest

from modules.chaos import run_local


def _browser():
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        return p, p.chromium.launch()
    except Exception:
        return None, None


@pytest.fixture(scope="module")
def page():
    p, browser = _browser()
    if browser is None:
        pytest.skip("Playwright Chromium not installed")
    pg = browser.new_page()
    yield pg
    browser.close()
    p.stop()


@pytest.mark.parametrize("mode", ["rename", "rewrap", "move", "hide", "popup"])
def test_mode_keeps_values_and_is_repeatable(page, mode):
    log, out = run_local.run_once(page, mode, 7)
    again, _ = run_local.run_once(page, mode, 7)
    out.pop("_ms")
    assert {k: out[k] for k in run_local.VALUES} == run_local.VALUES
    assert log and log == again


def test_rename_changes_labels_but_not_names_or_ids(page):
    page.goto(run_local.FORM)
    page.evaluate(run_local.SCRIPT)
    before = page.evaluate("[...document.querySelectorAll('input,select')].map(e => [e.name, e.id])")
    log = page.evaluate("o => window.__chaos(o)", {"mode": "rename", "seed": 3, "count": 9})
    after = page.evaluate("[...document.querySelectorAll('input,select')].map(e => [e.name, e.id])")
    assert before == after and all(e["from"] != e["to"] for e in log)
    assert page.evaluate("window.__chaosLog.length") == len(log)
