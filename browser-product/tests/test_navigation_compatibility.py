import asyncio
import base64
import os
import secrets
import threading
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
from browser import core_compat as core,worker as w
from browser.general import GeneralContext,observe,act,origin
from browser.general_routes import contexts
from browser.protocol import BrowserAction

@asynccontextmanager
async def fixture(html):
    async with async_playwright() as pw:
        kwargs={'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser=await pw.chromium.launch(headless=True,**kwargs)
        context=await browser.new_context();page=await context.new_page();await page.set_content(html)
        ctx=GeneralContext(context=context,page=page,allowed=set());ctx.permitted=lambda url:url=='about:blank'
        contexts[ctx.id]=ctx;sid=secrets.token_urlsafe(20);core.bridges[sid]=core.BridgeSession(ctx.id,'fixture')
        try:yield sid,ctx,page
        finally:await core.close(sid,w.INTERNAL_KEY);await browser.close()

@pytest.mark.asyncio
async def test_census_resolves_multiple_accessible_label_references():
    html='<span id="first">Account</span><span id="second">number</span><input aria-labelledby="first second">'
    async with fixture(html) as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert any(n['name']=='Account number' for n in snap['nodes'])

@pytest.mark.asyncio
async def test_hidden_links_do_not_consume_visible_budget_and_links_can_be_queried():
    hidden=''.join(f'<a style="display:none" href="/hidden{i}">Hidden {i}</a>' for i in range(100))
    visible=''.join(f'<a href="/item{i}">Item {i}</a>' for i in range(200))
    async with fixture(hidden+'<a href="/missions">Missions</a>'+visible) as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert any(n['name']=='Missions' for n in snap['nodes'])
        assert len(snap['nodes'])==160 and snap['observation_truncated']
        more=await core.snapshot(sid,w.INTERNAL_KEY,link_offset=160)
        assert any(n['name']=='Item 199' for n in more['nodes'])
        found=await core.snapshot(sid,w.INTERNAL_KEY,link_query='Item 199')
        assert [n['name'] for n in found['nodes']]==['Item 199']

@pytest.mark.asyncio
async def test_unrelated_clock_changes_do_not_block_but_changed_target_does():
    html='<p id="clock">Tick 1</p><button onclick="window.clicked=true">Open menu</button>'
    async with fixture(html) as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY);button=snap['nodes'][0]
        await page.locator('#clock').inner_text()
        await page.locator('#clock').evaluate("e=>e.innerText='Tick 2'")
        result=await core.action(sid,core.CoreAction(type='click',target=core.Target(role=button['role'],name=button['name']),action_id='clock-action'),w.INTERNAL_KEY)
        assert result['ok'] and await page.evaluate('window.clicked')
        await core.snapshot(sid,w.INTERNAL_KEY)
        await page.locator('button').evaluate("e=>e.innerText='Different action'")
        with pytest.raises(HTTPException) as stale:
            await core.action(sid,core.CoreAction(type='click',target=core.Target(role=button['role'],name=button['name']),action_id='changed-action'),w.INTERNAL_KEY)
        assert stale.value.status_code==409

@pytest.mark.asyncio
async def test_core_check_select_and_state_metadata_require_real_source():
    html='''<label>Consent<input type="checkbox"></label>
      <label>Choice<select><option value="one">One</option><option value="two">Two</option></select></label>
      <label>Disabled<input disabled></label><label>Readonly<input readonly value="fixed"></label>'''
    async with fixture(html) as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        check=next(n for n in snap['nodes'] if n['role']=='checkbox')
        assert check['checked'] is False
        req=core.CoreAction(type='check',target=core.Target(role=check['role'],name=check['name']),checked=True)
        with pytest.raises(HTTPException) as missing:await core.action(sid,req,w.INTERNAL_KEY)
        assert missing.value.status_code==422
        await core.action(sid,req.model_copy(update={'verified':True,'source_ref':'citizen-test-answer'}),w.INTERNAL_KEY)
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert next(n for n in snap['nodes'] if n['role']=='checkbox')['checked'] is True
        select=next(n for n in snap['nodes'] if n['role']=='combobox')
        value=select['options'][1]['value']
        await core.action(sid,core.CoreAction(type='select',target=core.Target(role=select['role'],name=select['name']),value=value,verified=True,source_ref='citizen-test-answer'),w.INTERNAL_KEY)
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert next(n for n in snap['nodes'] if n['role']=='combobox')['value']=='two'
        assert next(n for n in snap['nodes'] if n['name']=='Disabled')['disabled']
        assert next(n for n in snap['nodes'] if n['name']=='Readonly')['readonly']

@pytest.mark.asyncio
async def test_core_exposes_and_switches_real_popup_tab():
    async with fixture('''<button onclick="const p=window.open('about:blank');p.document.write('<title>Child</title><p>Popup page</p>')">Open popup</button>''') as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY);node=snap['nodes'][0]
        await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        popup=next(t for t in snap['tabs'] if not t['active'])
        await core.action(sid,core.CoreAction(type='switch_tab',tab_id=popup['id']),w.INTERNAL_KEY)
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert snap['title']=='Child' and 'Popup page' in snap['page_text']

@pytest.mark.asyncio
async def test_blocked_and_empty_pages_are_explicit_not_normal_success():
    async with fixture('<title>Just a moment...</title><p>Performing security verification</p>') as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert snap['page_status']=='blocked' and snap['error']=='blocked'
        assert snap['human_signals']
        await page.set_content('<html><body></body></html>')
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert snap['page_status']=='loading_or_empty'


@pytest.mark.asyncio
async def test_login_controls_are_human_only_and_secrets_remain_redacted_after_page_change():
    html='''<form action="https://fixture.test/login" method="post" onsubmit="event.preventDefault();document.body.innerHTML='<p>Signed in synthetic-secret-password</p>'">
      <label>Email<input name="email" type="email"></label>
      <label>Password<input name="password" type="password"></label>
      <button type="submit">Sign in</button></form>'''
    async with fixture(html) as (sid,ctx,page):
        snap=await core.snapshot(sid,w.INTERNAL_KEY);button=next(n for n in snap['nodes'] if n['name']=='Sign in')
        assert button['action_category']=='auth_submit'
        with pytest.raises(HTTPException):await core.action(sid,core.CoreAction(type='click',target=core.Target(role=button['role'],name=button['name'])),w.INTERNAL_KEY)
        task='human-login-fixture'
        await core.human_begin(sid,core.HumanBegin(task_id=task,reason='login'),w.INTERNAL_KEY)
        view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
        for label,value in [('Email','synthetic@example.invalid'),('Password','synthetic-secret-password')]:
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            node=next(n for n in view['controls'] if n['label']==label)
            await core.human_act(sid,core.HumanAction(task_id=task,kind='fill',target_ref=node['ref'],value=value),w.INTERNAL_KEY)
        view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
        node=next(n for n in view['controls'] if n['category']=='auth_submit')
        await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=node['ref']),w.INTERNAL_KEY)
        done=await core.human_finish(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
        assert done['verified'] is False
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        assert 'synthetic-secret-password' not in str(snap) and '[redacted]' in snap['page_text']

@pytest.mark.asyncio
async def test_v2_dedicated_upload_confirmation_sends_real_multipart_post(monkeypatch):
    posted=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<form method="post" action="/upload" enctype="multipart/form-data"><label>File<input type="file" name="file"></label><button type="submit">Upload</button></form>')
        def do_POST(self):
            posted.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<p>File upload confirmed</p>')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.delenv('BROWSER_INTERMEDIATE_POST_ORIGINS',raising=False)
    async with async_playwright() as pw:
        options={'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser=await pw.chromium.launch(headless=True,**options)
        context=await browser.new_context();page=await context.new_page()
        ctx=GeneralContext(context=context,page=page,allowed={origin(base)});await context.route('**/*',ctx.route)
        try:
            await page.goto(base);obs=await observe(ctx)
            file=next(e for e in obs['elements'] if e['type']=='file')
            await page.locator('input').set_input_files({'name':'fixture.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4 fixture'})
            obs=await observe(ctx);button=next(e for e in obs['elements'] if e['label']=='Upload')
            result=await act(ctx,BrowserAction(action_id='v2-upload-confirm',observation_id=obs['observation_id'],kind='click',target_ref=button['ref']))
            assert len(posted)==1 and b'%PDF-1.4 fixture' in posted[0]
            assert 'File upload confirmed' in result['observation']['text']
        finally:await browser.close();server.shutdown();server.server_close()


@pytest.mark.asyncio
async def test_reviewed_native_submit_is_single_use_and_unverified_result_stops_writes(monkeypatch):
    from browser.general import watch_navigation
    from urllib.parse import urlsplit
    import json
    submitted=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urlsplit(self.path).path
            if path=='/submitted':submitted.append(self.path)
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<p>Received synthetic form</p>' if path=='/submitted' else b'<form action="/submitted" method="get"><input type="hidden" name="csrf" value="private-csrf-test"><label>Name<input name="name" value="Synthetic"></label><button type="submit">Submit</button></form>')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','true')
    monkeypatch.setenv('BROWSER_FINAL_SUBMIT_TARGETS_JSON',json.dumps([{'url':base+'/submitted','method':'GET'}]))
    monkeypatch.setattr(w,'MODE','integrated')
    async with async_playwright() as pw:
        options={'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser=await pw.chromium.launch(headless=True,**options)
        context=await browser.new_context();page=await context.new_page()
        ctx=GeneralContext(context=context,page=page,allowed={origin(base)})
        watch_navigation(ctx);await context.route('**/*',ctx.route);await page.goto(base)
        contexts[ctx.id]=ctx;sid=secrets.token_urlsafe(16);core.bridges[sid]=core.BridgeSession(ctx.id,'fixture')
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY);node=next(n for n in snap['nodes'] if n['name']=='Submit')
            req=core.CoreAction(type='click',action_id='native-submit-action',target=core.Target(role=node['role'],name=node['name']))
            with pytest.raises(HTTPException) as denied:await core.action(sid,req,w.INTERNAL_KEY)
            assert denied.value.status_code==403 and not submitted
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await core.authorize(sid,core.Authorization(approved=True,approval_ref='citizen-review-fixture',review_observation_id=snap['observation_id']),w.INTERNAL_KEY)
            await page.locator('input[type=hidden]').evaluate("e=>e.value='changed-private-csrf'")
            with pytest.raises(HTTPException) as changed:await core.action(sid,req,w.INTERNAL_KEY)
            assert changed.value.status_code==409 and not submitted
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            assert 'changed-private-csrf' not in json.dumps(snap)
            await core.authorize(sid,core.Authorization(approved=True,approval_ref='new-citizen-review-fixture',review_observation_id=snap['observation_id']),w.INTERNAL_KEY)
            result=await core.action(sid,req,w.INTERNAL_KEY)
            assert result['request_observed'] and result['confirmed_by_portal'] is False
            assert len(submitted)==1 and (await core.snapshot(sid,w.INTERNAL_KEY))['needs_reconciliation']
            assert (await core.action(sid,req,w.INTERNAL_KEY))['replayed']
            with pytest.raises(HTTPException):await core.action(sid,req.model_copy(update={'action_id':'different-action'}),w.INTERNAL_KEY)
            assert len(submitted)==1
        finally:await core.close(sid,w.INTERNAL_KEY);await browser.close();server.shutdown();server.server_close()
