import asyncio
import base64
import os
import secrets
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
from browser import core_compat as core, worker as w
from browser.general import GeneralContext
from browser.general_routes import contexts
from browser.document_validation import validate_document


@pytest.mark.parametrize('raw,name,mime',[(b'garbage','x.png','image/png'),(b'garbage','x.jpg','image/jpeg'),(b'%PDF-1.4','x.png','application/pdf'),(b'%PDF-1.4','../x.pdf','application/pdf')])
def test_invalid_prepared_document_rejected(raw,name,mime):
    with pytest.raises(HTTPException):validate_document(raw,name,mime)


@pytest.mark.asyncio
async def test_duplicate_concurrent_action_and_changed_payload(monkeypatch):
    ctx=SimpleNamespace(lock=asyncio.Lock())
    info=core.BridgeSession('fixture-context','fixture')
    monkeypatch.setitem(contexts,info.context_id,ctx)
    monkeypatch.setitem(core.bridges,'audit-session',info)
    calls=[]
    async def effect(sid,req,info,ctx):
        calls.append(req.type);await asyncio.sleep(.01);return {'ok':True}
    monkeypatch.setattr(core,'action_locked',effect)
    req=core.CoreAction(type='click',action_id='stable-action-123')
    results=await asyncio.gather(*(core.action('audit-session',req,w.INTERNAL_KEY) for _ in range(3)))
    assert len(calls)==1 and sum(x.get('replayed',False) for x in results)==2
    with pytest.raises(HTTPException) as changed:
        await core.action('audit-session',core.CoreAction(type='wait',action_id=req.action_id),w.INTERNAL_KEY)
    assert changed.value.status_code==409
    monkeypatch.setattr(w,'MODE','integrated')
    with pytest.raises(HTTPException) as missing:
        await core.action('audit-session',core.CoreAction(type='click'),w.INTERNAL_KEY)
    assert missing.value.status_code==422


@pytest.mark.asyncio
async def test_uncertain_effect_blocks_a_new_action_id(monkeypatch):
    ctx=SimpleNamespace(lock=asyncio.Lock())
    info=core.BridgeSession('uncertain-context','fixture')
    monkeypatch.setitem(contexts,info.context_id,ctx);monkeypatch.setitem(core.bridges,'uncertain-session',info)
    async def unknown(sid,req,info,ctx):
        info.effect_started=True;raise RuntimeError('unknown portal outcome')
    monkeypatch.setattr(core,'action_locked',unknown)
    with pytest.raises(RuntimeError):
        await core.action('uncertain-session',core.CoreAction(type='click',action_id='first-action'),w.INTERNAL_KEY)
    with pytest.raises(HTTPException) as blocked:
        await core.action('uncertain-session',core.CoreAction(type='click',action_id='second-action'),w.INTERNAL_KEY)
    assert blocked.value.status_code==409


@pytest.mark.asyncio
async def test_real_dom_expiry_otp_limits_brackets_and_upload_label(monkeypatch):
    async with async_playwright() as pw:
        options={'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser=await pw.chromium.launch(headless=True,**options)
        context=await browser.new_context();page=await context.new_page()
        await page.set_content('''<label>Amount [INR]<input id="amount"></label>
          <label>OTP<input id="otp"></label><button type="button" onclick="window.verifies=(window.verifies||0)+1">Verify OTP</button>
          <form action="https://fixture.test/upload" method="post"><input type="file"><input type="submit" name="commit" value="Upload"></form>
          <img id="captcha_image" width="80" height="40" src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" onclick="window.clicked=true">''')
        ctx=GeneralContext(context=context,page=page,allowed=set());ctx.permitted=lambda u:u=='about:blank'
        contexts[ctx.id]=ctx;sid=secrets.token_urlsafe(20);info=core.BridgeSession(ctx.id,'fixture');core.bridges[sid]=info
        async def action(kind,name,value=None):
            snap=await core.snapshot(sid,w.INTERNAL_KEY);node=next(x for x in snap['nodes'] if x['name']==name)
            return await core.action(sid,core.CoreAction(type=kind,target=core.Target(role=node['role'],name=name),value=value,action_id=secrets.token_urlsafe(16)),w.INTERNAL_KEY)
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            assert next(x for x in snap['nodes'] if x['name']=='Upload')['action_category']=='upload_step'
            await action('type','Amount [INR]','123')
            assert await page.locator('#amount').input_value()=='123'
            for _ in range(5):
                await action('type','OTP','000000');await action('click','Verify OTP')
            await action('type','OTP','000000')
            with pytest.raises(HTTPException) as limited:await action('click','Verify OTP')
            assert limited.value.status_code==429 and info.otp_verify_count==5
            assert await page.evaluate('window.verifies')==5
            info.human_task_id='expired-task';info.human_expires=time.time()-1
            await core.human_begin(sid,core.HumanBegin(task_id='replacement-task',expires_at=time.time()+120),w.INTERNAL_KEY)
            assert info.human_task_id=='replacement-task'
            view=await core.human_view(sid,core.HumanBegin(task_id='replacement-task'),w.INTERNAL_KEY)
            verify=next(x for x in view['controls'] if x['category']=='otp_verify')
            with pytest.raises(HTTPException) as shared:
                await core.human_act(sid,core.HumanAction(task_id='replacement-task',kind='click',target_ref=verify['ref']),w.INTERNAL_KEY)
            assert shared.value.status_code==429
            # Expire while waiting for ownership: action must recheck inside lock.
            info.human_expires=time.time()+.1
            box=await page.locator('#captcha_image').bounding_box()
            await ctx.lock.acquire()
            queued=asyncio.create_task(core.human_act(sid,core.HumanAction(task_id='replacement-task',kind='challenge_click',x=box['x']+2,y=box['y']+2),w.INTERNAL_KEY))
            await asyncio.sleep(.2);ctx.lock.release()
            with pytest.raises(HTTPException) as expired:await queued
            assert expired.value.status_code==403 and not await page.evaluate('!!window.clicked')
        finally:await core.close(sid,w.INTERNAL_KEY);await browser.close()


@pytest.mark.asyncio
async def test_handoff_failed_begin_is_visible_for_reconciliation(tmp_path,monkeypatch):
    from server import app,core_assist
    monkeypatch.setattr(app,'DB',tmp_path/'assist.db');monkeypatch.setattr(app,'audit',lambda *a,**k:None)
    async def uncertain(*args,**kwargs):raise HTTPException(504,'worker outcome unknown')
    monkeypatch.setattr(app,'worker',uncertain)
    with pytest.raises(HTTPException):await core_assist.offer('fixture-session',core_assist.Offer(reason='otp'),None,app.KEY)
    with app.conn() as db:row=db.execute('SELECT state,token_hash FROM core_assist_tasks').fetchone()
    assert row['state']=='needs_reconciliation' and len(row['token_hash'])==64


def test_release_contains_integrated_compose_and_excludes_private_data():
    import zipfile
    from scripts.package_release import package
    with zipfile.ZipFile(package()) as archive:
        names=archive.namelist()
        assert 'gradientzero-browser/compose.integrated.yaml' in names
        assert not any('/data/' in n or n.endswith('/.env') or 'browser-test-results' in n for n in names)


@pytest.mark.asyncio
async def test_helper_preserves_id_after_lost_response():
    import httpx
    from clients.core_browser import CoreBrowserClient
    posts=[]
    def handler(request):
        if request.method=='GET':return httpx.Response(200,json={})
        posts.append(request.content)
        if len(posts)==1:raise httpx.ReadTimeout('lost response',request=request)
        return httpx.Response(200,json={'ok':True,'replayed':True})
    async def decide(snapshot):return {'type':'click'}
    async with CoreBrowserClient('http://fixture','key',transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):await client.step('sid',decide)
        with pytest.raises(RuntimeError):await client.step('sid',decide)
        assert (await client.retry_pending('sid'))['replayed']
    assert len(posts)==2 and posts[0]==posts[1]


@pytest.mark.asyncio
async def test_core_context_blocks_websockets_and_service_workers(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<html><body>Read-only test</body></html>')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE','allowlist')
    monkeypatch.setenv('BROWSER_ALLOWED_ORIGINS',base)
    monkeypatch.setenv('MAX_BROWSER_TABS','2')
    monkeypatch.setattr(core,'settings',lambda:{'fixture':{'url':base}})
    async with async_playwright() as pw:
        options={'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}
        browser=await pw.chromium.launch(headless=True,**options)
        monkeypatch.setattr(w.app.state,'browser',browser,raising=False)
        sid=None
        try:
            sid=(await core.open_session(core.Open(portal_id='fixture'),w.INTERNAL_KEY))['session_id']
            _,ctx=core.get(sid)
            sw=await ctx.page.evaluate("navigator.serviceWorker.register('/sw.js').then(()=>true,()=>false)")
            ws=await ctx.page.evaluate("""()=>new Promise(resolve=>{
              const s=new WebSocket(location.origin.replace('http:','ws:')+'/socket');
              s.onopen=()=>{s.close();resolve(true)};s.onclose=()=>resolve(false);s.onerror=()=>resolve(false);
              setTimeout(()=>resolve(false),1000);
            })""")
            assert await ctx.page.evaluate('navigator.serviceWorker.controller === null')
            assert ws is False
            assert '/sw.js' not in requests and '/socket' not in requests
            for _ in range(3):
                try:await ctx.context.new_page()
                except Exception:pass  # Excess pages may close before new_page returns.
            await asyncio.sleep(.1)
            assert len(ctx.context.pages)<=2 and not ctx.page.is_closed()
        finally:
            if sid:await core.close(sid,w.INTERNAL_KEY)
            await browser.close();server.shutdown();server.server_close()


@pytest.mark.asyncio
async def test_v2_failed_setup_closes_context(monkeypatch):
    from browser import general_routes
    from browser.protocol import ContextStart
    from playwright.async_api import Error
    class Context:
        closed=False
        async def new_page(self):raise Error('new page failed')
        async def close(self):self.closed=True
    context=Context()
    class Browser:
        async def new_context(self,**kwargs):return context
    monkeypatch.setattr(w.app.state,'browser',Browser(),raising=False)
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE','allowlist')
    monkeypatch.setenv('BROWSER_ALLOWED_ORIGINS','http://127.0.0.1:8100')
    req=ContextStart(request_id='fixture-request',subject='fixture-user',consent_ref='fixture-consent',url='http://127.0.0.1:8100')
    with pytest.raises(HTTPException) as error:await general_routes.create(req,w.INTERNAL_KEY)
    assert error.value.status_code==502 and context.closed
