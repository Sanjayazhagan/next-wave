"""Verify the running synthetic system using HTTP and the actual dashboard browser.
Run after scripts/run_local.py. Writes reproducible local-only evidence.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

BASE = os.getenv('BASE_URL', 'http://127.0.0.1:8100').rstrip('/')
OUT = Path('output/local-verification')


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    async with httpx.AsyncClient(base_url=BASE, timeout=45) as c:
        async def call(method, path, data=None, status=200):
            r = await c.request(method, path, json=data)
            assert r.status_code == status, (path, r.status_code, r.text)
            return r.json()

        # Independent full synthetic runs; hidden fields must stop safely.
        for chaos in (() if '--ui-only' in sys.argv else ('none', 'rename_income', 'popup', 'server_failure', 'move_button', 'expire_session', 'hide_income')):
            for run in range(1, 6):
                start = time.monotonic()
                s = await call('POST', '/api/sessions', {'consent': True})
                root = '/api/sessions/' + s['id']
                try:
                    await call('POST', root+'/approve', {'confirmed': True, 'review_hash': 'invalid'}, 409)
                    assert not (await call('POST', root+'/otp', {'otp': 'wrong'}))['ok']
                    await call('POST', root+'/otp', {'otp': '246810'})
                    assert not (await call('POST', root+'/human', {'challenge_answer': 'wrong'}))['ok']
                    await call('POST', root+'/human', {'challenge_answer': '7'})
                    if chaos != 'none':
                        await call('POST', '/session/'+s['id']+'/inject', {'script_name': chaos})
                    if chaos == 'expire_session':
                        await call('POST', root+'/otp', {'otp': '246810'})
                        await call('POST', root+'/human', {'challenge_answer': '7'})
                    review = await call('POST', root+'/fill')
                    if chaos == 'hide_income':
                        assert review['state'] == 'human_takeover'
                        await call('POST', root+'/approve', {'confirmed': True, 'review_hash': 'invalid'}, 409)
                    else:
                        assert review['state'] == 'approval_needed'
                        if chaos == 'none':
                            profile = {x['name']: x['value'] for x in (await call('GET', root+'/fields'))['fields']}
                            profile['income'] = '125000'
                            await call('POST', root+'/edit', {'profile': profile})
                            await call('POST', root+'/approve', {'confirmed': True, 'review_hash': review['review_hash']}, 409)
                            review = await call('POST', root+'/fill')
                        submitted = await call('POST', root+'/approve', {'confirmed': True, 'review_hash': review['review_hash']})
                        assert submitted['receipt_id'].startswith('MOCK-')
                        assert (await call('POST', root+'/poll'))['status'] == 'submitted'
                        await call('POST', root+'/approve', {'confirmed': True, 'review_hash': review['review_hash']}, 409)
                        assert (await c.get(root+'/receipt.pdf')).content.startswith(b'%PDF-')
                    events = await call('GET', root+'/audit')
                    assert '246810' not in json.dumps(events)
                    results.append({'chaos': chaos, 'run': run, 'result': 'safe_stop' if chaos == 'hide_income' else 'submitted_mock', 'seconds': round(time.monotonic()-start, 2)})
                    print(results[-1], flush=True)
                finally:
                    await call('DELETE', root)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.set_default_timeout(60000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(BASE)
            await page.get_by_role('checkbox').check()
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Start secure demo').click()
            await page.locator('#otp-val').fill('246810')
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Verify entered OTP').click()
            await page.locator('#human-val').fill('7')
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Continue after human verification').click()
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Rename a field').click()
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Auto-fill and verify review').click()
            await page.locator('#active-control input[name=income]').fill('130000')
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Save edits and prepare fresh review').click()
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='Auto-fill and verify review').click()
            await page.reload()
            await page.wait_for_function('!busy')
            await page.get_by_role('button', name='I approve').click()
            await page.get_by_text('Receipt captured', exact=True).wait_for()
            await page.locator('#frame img').wait_for()
            await page.screenshot(path=str(OUT/'dashboard-submitted.png'), full_page=True)
            assert not errors, errors
            # Mobile rendering and preserved session state.
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.screenshot(path=str(OUT/'dashboard-mobile.png'), full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await browser.close()
    report = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'environment': 'local Windows / real HTTP / Playwright Chromium', 'portal_type': 'mock', 'runs': results, 'dashboard_e2e': 'passed', 'deployment': 'deferred by user'}
    (OUT/('ui-results.json' if '--ui-only' in sys.argv else 'results.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'PASS: {len(results)} HTTP scenarios plus desktop/mobile dashboard E2E', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
