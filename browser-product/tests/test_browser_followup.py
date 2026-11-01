import os
import secrets
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from playwright.async_api import Error as PlaywrightError, async_playwright
from browser import core_compat as core, worker as w
from browser.general import GeneralContext
from browser.general_routes import contexts
from clients.core_browser import CoreBrowserClient


@pytest.mark.asyncio
async def test_failed_new_page_closes_context_and_reports_safe_reason(monkeypatch):
    class Context:
        closed = False
        async def new_page(self):
            raise PlaywrightError('net::ERR_CONNECTION_REFUSED private-url?secret=value')
        async def close(self):
            self.closed = True
    context = Context()
    class Browser:
        async def new_context(self, **kwargs):
            return context
    monkeypatch.setattr(w.app.state, 'browser', Browser(), raising=False)
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE', 'allowlist')
    monkeypatch.setenv('BROWSER_ALLOWED_ORIGINS', 'http://127.0.0.1:8100')
    monkeypatch.setattr(core, 'settings', lambda: {'fixture': {'url': 'http://127.0.0.1:8100'}})
    before = set(contexts)
    with pytest.raises(HTTPException) as error:
        await core.open_session(core.Open(portal_id='fixture'), w.INTERNAL_KEY)
    assert error.value.status_code == 502
    assert context.closed and set(contexts) == before
    assert 'connection_failure' in error.value.detail and 'reference=' in error.value.detail
    assert 'private-url' not in error.value.detail and 'secret' not in error.value.detail


@pytest.mark.asyncio
async def test_explicit_url_and_consent_reach_core_gateway_without_demo_fallback():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'session_id': 'fixture'})
    async with CoreBrowserClient('http://fixture', 'test', transport=httpx.MockTransport(handler)) as client:
        assert (await client.open_url('https://example.org/request', 'citizen-consent'))['session_id'] == 'fixture'
        with pytest.raises(ValueError):
            await client.open_url('https://example.org/request', '')
    assert len(requests) == 1
    assert requests[0].url.path == '/core-browser/session'
    assert b'https://example.org/request' in requests[0].content
    assert b'portal_id' not in requests[0].content


@pytest.mark.asyncio
async def test_data_url_captcha_identity_and_stale_human_click():
    async with async_playwright() as pw:
        kwargs = {'executable_path': os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser = await pw.chromium.launch(headless=True, **kwargs)
        context = await browser.new_context()
        page = await context.new_page()
        await page.set_content('''<img id="captcha_image" width="120" height="60"
          src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="
          onclick="this.dataset.clicked='yes'">
          <label>CAPTCHA<input></label>''')
        ctx = GeneralContext(context=context, page=page, allowed=set())
        ctx.permitted = lambda url: url == 'about:blank'
        contexts[ctx.id] = ctx
        sid = secrets.token_urlsafe(20)
        core.bridges[sid] = core.BridgeSession(ctx.id, 'fixture')
        task = 'fixture-human-task'
        try:
            await core.human_begin(sid, core.HumanBegin(task_id=task, expires_at=time.time()+120), w.INTERNAL_KEY)
            view = await core.human_view(sid, core.HumanBegin(task_id=task), w.INTERNAL_KEY)
            box = await page.locator('#captcha_image').bounding_box()
            assert box in view['challenge_boxes']
            await page.locator('body').evaluate("e=>e.insertAdjacentHTML('afterbegin','<p>Updated</p>')")
            with pytest.raises(HTTPException) as stale:
                await core.human_act(sid, core.HumanAction(task_id=task, observation_id=view['observation_id'], kind='challenge_click', x=box['x']+2, y=box['y']+2), w.INTERNAL_KEY)
            assert stale.value.status_code == 409
            view = await core.human_view(sid, core.HumanBegin(task_id=task), w.INTERNAL_KEY)
            box = await page.locator('#captcha_image').bounding_box()
            await core.human_act(sid, core.HumanAction(task_id=task, observation_id=view['observation_id'], kind='challenge_click', x=box['x']+2, y=box['y']+2), w.INTERNAL_KEY)
            assert await page.locator('#captcha_image').get_attribute('data-clicked') == 'yes'
        finally:
            await core.close(sid, w.INTERNAL_KEY)
            await browser.close()
