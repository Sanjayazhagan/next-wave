"""Self-contained real HTTP/mobile handoff test on isolated local ports."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import httpx
from playwright.async_api import async_playwright


async def main():
    root = Path(__file__).resolve().parents[1]
    out = root/'output'/'human-handoff'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, PYTHONUTF8='1', MOCK_BASE_URL='http://127.0.0.1:8200', WORKER_URL='http://127.0.0.1:8201', DATABASE_PATH=str(Path(tmp)/'test.db'))
        processes = []
        log = (out/'services.log').open('w', encoding='utf-8')
        try:
            for module, port in [('server.app:app', '8200'), ('browser.worker:app', '8201')]:
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', port], cwd=root, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8200', timeout=40) as c:
                for _ in range(100):
                    try:
                        if (await c.get('/health')).is_success:
                            async with httpx.AsyncClient() as worker:
                                if (await worker.get('http://127.0.0.1:8201/health')).is_success:
                                    break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.2)
                else:
                    raise RuntimeError('Services failed to start; inspect services.log')
                async def post(path, body):
                    r = await c.post(path, json=body, headers={'X-Internal-Key': env.get('INTERNAL_KEY', 'demo-worker-key-change-before-production')})
                    r.raise_for_status()
                    return r.json()
                sid = (await post('/api/sessions', {'consent': True}))['id']
                await post(f'/api/sessions/{sid}/otp', {'otp': '246810'})
                task = await post('/integration/v1/human-tasks', {'session_id': sid})
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch()
                    page = await browser.new_page(viewport={'width': 390, 'height': 844})
                    await page.goto('http://127.0.0.1:8200'+task['assistance_path'])
                    await page.get_by_role('button', name='Open verification').click()
                    await page.locator('#screen').wait_for(state='visible')
                    await page.screenshot(path=str(out/'challenge-mobile.png'))
                    await page.get_by_label('Your answer').fill('7')
                    await page.get_by_role('button', name='Verify and continue').click()
                    await page.locator('#done').wait_for(state='visible')
                    await page.screenshot(path=str(out/'completed-mobile.png'))
                    assert not await page.evaluate('location.hash')
                    await browser.close()
                assert (await c.get(f'/api/sessions/{sid}')).json()['state'] == 'form_ready'
                review = await post(f'/api/sessions/{sid}/fill', {})
                receipt = await post(f'/api/sessions/{sid}/approve', {'confirmed': True, 'review_hash': review['review_hash']})
                assert receipt['receipt_id'].startswith('MOCK-')
                (out/'result.json').write_text(json.dumps({'mode': 'demo', 'mobile_handoff': 'passed', 'same_browser_continued_to_mock_receipt': True, 'whatsapp_message_sent': False}, indent=2), encoding='utf-8')
                print('PASS: real HTTP mobile challenge handoff, same-browser resume and approved mock receipt')
        finally:
            for p in processes:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait()
            log.close()


if __name__ == '__main__':
    asyncio.run(main())
