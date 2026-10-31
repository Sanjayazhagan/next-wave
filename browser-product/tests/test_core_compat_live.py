"""Browser-level contract test with a synthetic, fully local portal.

No government portal, identity data, LLM, or paid account is used.
"""
import asyncio
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright, Error as PlaywrightError
from browser import worker as w
from browser import core_compat as core

HTML=b'''<!doctype html><html><head><title>Local Scholarship Test</title></head>
<body><a href="/form">Open scholarship form</a></body></html>'''
FORM=b'''<!doctype html><html><head><title>Scholarship Application</title></head><body>
<label for="name">Student Name</label><input id="name" />
<button type="button" onclick="document.getElementById('review').hidden=false">Next</button>
<section id="review" hidden><h2>Review your details</h2>
<button type="submit" onclick="document.getElementById('result').hidden=false">Submit application</button></section>
<p id="result" hidden>Successfully submitted application. Application received: REF-DEMO-123</p>
</body></html>'''

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        raw=FORM if self.path=='/form' else HTML
        self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass

@pytest.mark.asyncio
async def test_live_langgraph_bridge(monkeypatch):
    server=ThreadingHTTPServer(('127.0.0.1',0),H)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    monkeypatch.setenv('BROWSER_ALLOWED_ORIGINS',base)
    monkeypatch.setenv('BROWSER_PORTALS_JSON','{"local":{"url":"'+base+'/","receipt_pattern":"Application received: (REF-DEMO-[0-9]+)"}}')
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','true')
    from browser.general_routes import contexts
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        w.app.state.browser=browser
        try:
            with pytest.raises(HTTPException) as exc:
                await core.open_session(core.Open(portal_id='unknown'),w.INTERNAL_KEY)
            assert exc.value.status_code==422
            try:
                sid=(await core.open_session(core.Open(portal_id='local'),w.INTERNAL_KEY))['session_id']
            except (PlaywrightError, HTTPException) as exc:
                if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc) or 'environment_blocked_by_admin' in str(exc):
                    pytest.skip('This runner blocks Chromium URL navigation; run in Docker/VM')
                raise
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            assert snap['url']==base+'/'
            async def click(text):
                nonlocal snap
                node=next(n for n in snap['nodes'] if n['name']==text)
                res=await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
                assert res['ok']
                snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await click('Open scholarship form')
            assert snap['url']==base+'/form'
            node=next(n for n in snap['nodes'] if n['name']=='Student Name')
            await core.action(sid,core.CoreAction(type='type',target=core.Target(role=node['role'],name=node['name']),value='Demo Student'),w.INTERNAL_KEY)
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await click('Next')
            with pytest.raises(HTTPException) as exc:
                await click('Submit application')
            assert exc.value.status_code==403
            assert (await core.snapshot(sid,w.INTERNAL_KEY))['receipt_number'] is None
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await core.authorize(sid,core.Authorization(approved=True,approval_ref='trusted-core-session-id',review_observation_id=snap['observation_id']),w.INTERNAL_KEY)
            await click('Submit application')
            assert snap['receipt_number']=='REF-DEMO-123'
            with pytest.raises(HTTPException) as exc:
                await click('Submit application')
            assert exc.value.status_code==403
            await core.close(sid,w.INTERNAL_KEY)
            with pytest.raises(HTTPException):await core.snapshot(sid,w.INTERNAL_KEY)
        finally:
            for bridge in list(core.bridges):await core.close(bridge,w.INTERNAL_KEY)
            await browser.close()
            server.shutdown();server.server_close()
