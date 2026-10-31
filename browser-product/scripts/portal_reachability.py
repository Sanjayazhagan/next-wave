"""Read-only, public landing-page reachability probe from the BROWSER WORKER VM.

Designed for the work-split's Day-1 requirement. This does NOT authenticate,
submit forms, exercise private data, prove terms permit automation, or certify an
end-to-end government portal flow.

Run INSIDE worker container to test the actual server egress/browser environment:
  docker compose -f compose.yaml -f compose.vm.yaml exec -T worker \
      python scripts/portal_reachability.py > reachability-$(date +%F).json
"""
import argparse
import asyncio
import datetime as dt
import json
import os
from urllib.parse import urlparse

from playwright.async_api import async_playwright

PORTALS = {
    "national_scholarship": "https://scholarships.gov.in/Students",
    "digilocker_document_service_only": "https://www.digilocker.gov.in/",
    "tn_esevai": "https://tnesevai.tn.gov.in/Pages/EsevaiServiceListInstitution.aspx",
    "tn_bc_mbc_welfare": "https://bcmbcmw.tn.gov.in/welfschemes.htm",
    "myscheme_discovery_only": "https://www.myscheme.gov.in/",
}
ALLOWED_HOSTS = {urlparse(u).hostname for u in PORTALS.values()}


def assert_public_research_url(url: str) -> None:
    """Restrict this probe to curated official public landing pages."""
    parts = urlparse(url)
    if parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise ValueError('Only pre-approved official HTTPS portal hostnames are allowed')


async def probe_one(browser, key: str, url: str, timeout_ms: int) -> dict:
    assert_public_research_url(url)
    entry = {"name": key, "requested_url": url, "browser_loaded": False,
             "http_status": None, "final_url": None, "title": None,
             "manual_login_or_submission_verified": False,
             "notes": "Landing-page navigation only; no login or application submitted"}
    context = await browser.new_context(ignore_https_errors=False, accept_downloads=False)
    page = await context.new_page()
    try:
        response = await page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
        entry['http_status'] = response.status if response else None
        entry['final_url'] = page.url.split('?')[0]  # do not log query strings
        entry['title'] = (await page.title())[:160]
        entry['browser_loaded'] = response is not None and 200 <= response.status < 400
        if response is None:
            entry['notes'] = 'No main-document response; inspect manually'
        elif response.status >= 400:
            entry['notes'] = f'HTTP {response.status}: restricted or unavailable; inspect manually'
    except Exception as exc:
        # Never log personal-data-bearing URLs, cookies or page contents.
        entry['error_type'] = type(exc).__name__
        entry['notes'] = 'Navigation failed; verify browser egress, DNS, TLS, policy and portal uptime'
    finally:
        await context.close()
    return entry


async def run(timeout_ms: int) -> dict:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            for key, url in PORTALS.items():
                results.append(await probe_one(browser, key, url, timeout_ms))
        finally:
            await browser.close()
    return {
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "public landing pages only; no authentication or application execution",
        "region": os.getenv("VERIFIED_VM_REGION", "unverified/local"),
        "browser_worker_machine": "Execution location must be independently verified; this output alone does not prove Mumbai",
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout-ms', type=int, default=15000)
    args = parser.parse_args()
    if not 1000 <= args.timeout_ms <= 90000:
        parser.error('timeout-ms must be between 1000 and 90000')
    result = asyncio.run(run(args.timeout_ms))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if all(x['browser_loaded'] for x in result['results']) else 2)


if __name__ == '__main__':
    main()
