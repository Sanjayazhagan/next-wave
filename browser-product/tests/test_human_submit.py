import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import os
import secrets
import threading
import time
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
from browser import core_compat as core,worker as w
from browser.general import GeneralContext,origin,observe
from browser.general_routes import contexts

@asynccontextmanager
async def portal(confirmed=True):
    posts=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            body=('<p>Application successfully submitted. Receipt: DEMO-123</p>' if confirmed else '<p>Processing. Check later.</p>') if self.path=='/receipt' else '<form action="/submit" method="post"><input type="hidden" name="nonce" value="review-nonce"><label>Name<input name="name" value="Synthetic citizen"></label><button>Submit Application</button></form><button type="button">Help</button>'
            self.wfile.write(body.encode())
        def do_POST(self):
            posts.append(self.rfile.read(int(self.headers.get('Content-Length','0'))));self.send_response(303);self.send_header('Location','/receipt');self.end_headers()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    async with async_playwright() as pw:
        b=await pw.chromium.launch(**({'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}));c=await b.new_context();p=await c.new_page()
        ctx=GeneralContext(context=c,page=p,allowed={origin(url)});await c.route('**/*',ctx.route);await p.goto(url)
        sid=secrets.token_urlsafe(20);contexts[ctx.id]=ctx;info=core.BridgeSession(ctx.id,'fixture',receipt_pattern=r'Receipt: (DEMO-\d+)');core.bridges[sid]=info
        try:yield sid,ctx,p,info,posts
        finally:core.release_human(info,ctx);await core.close(sid,w.INTERNAL_KEY);await b.close();server.shutdown();server.server_close()

async def begin(sid,reason='submit'):
    snap=await core.snapshot(sid,w.INTERNAL_KEY);task='task-'+secrets.token_hex(8)
    target=next(n for n in snap['nodes'] if n['name']=='Submit Application')
    req=core.HumanBegin(task_id=task,reason=reason,review_observation_id=snap['observation_id'],approval_ref='approval-'+secrets.token_hex(8),target_ref=target['ref'])
    await core.human_begin(sid,req,w.INTERNAL_KEY)
    view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
    return task,target,view

@pytest.mark.asyncio
async def test_human_submit_single_use_receipt_with_automation_disabled(monkeypatch):
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','false')
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid)
        assert len(view['controls'])==1 and view['controls'][0]['category']=='final_submit'
        assert info.human_expires-time.time()>590 and ctx.human_lease_until==info.human_expires
        with pytest.raises(HTTPException):await core.close(sid,w.INTERNAL_KEY)
        req=core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id'])
        result=await core.human_act(sid,req,w.INTERNAL_KEY)
        assert result['state']=='completed' and result['confirmed_by_portal'] and result['receipt_number']=='DEMO-123'
        assert len(posts)==1 and ctx.human_lease_until==0 and not p.is_closed()
        with pytest.raises(HTTPException):await core.human_act(sid,req,w.INTERNAL_KEY)
        assert len(posts)==1
        status=await core.human_status(sid,w.INTERNAL_KEY);assert status['task_id']==task and status['result']==result

@pytest.mark.asyncio
async def test_non_submit_task_cannot_click_final():
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid,'captcha')
        with pytest.raises(HTTPException) as error:await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id']),w.INTERNAL_KEY)
        assert error.value.status_code==403 and not posts

@pytest.mark.asyncio
async def test_submit_task_rejects_typing_coordinates_and_other_clicks():
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid)
        for req in [core.HumanAction(task_id=task,kind='fill',value='other'),core.HumanAction(task_id=task,kind='challenge_click',x=1,y=1),core.HumanAction(task_id=task,kind='click',target_ref='not-the-submit',observation_id=view['observation_id'])]:
            with pytest.raises(HTTPException) as error:await core.human_act(sid,req,w.INTERNAL_KEY)
            assert error.value.status_code==403
        with pytest.raises(HTTPException):await core.human_finish(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
        assert not posts

@pytest.mark.asyncio
async def test_expired_link_cannot_submit():
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid);info.human_expires=time.time()-1
        with pytest.raises(HTTPException) as error:await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id']),w.INTERNAL_KEY)
        assert error.value.status_code==403 and not posts

@pytest.mark.asyncio
@pytest.mark.parametrize('change',["document.body.insertAdjacentHTML('beforeend','<p>Review changed</p>')","document.querySelector('input[type=hidden]').value='new-nonce'","document.querySelector('form').action='/other-submit'"])
async def test_changed_review_refuses_click_and_requires_new_review(change):
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid);await p.evaluate(change)
        with pytest.raises(HTTPException) as error:await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id']),w.INTERNAL_KEY)
        assert error.value.status_code==409 and not posts
        assert info.human_result['state']=='review_changed' and info.human_task_id is None

@pytest.mark.asyncio
async def test_uncertain_submission_blocks_new_submission():
    async with portal(confirmed=False) as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid)
        result=await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id']),w.INTERNAL_KEY)
        assert result['state']=='uncertain' and result['needs_reconciliation'] and not result['confirmed_by_portal']
        assert info.uncertain_action and len(posts)==1
        snap=await core.snapshot(sid,w.INTERNAL_KEY)
        with pytest.raises(HTTPException):await core.human_begin(sid,core.HumanBegin(task_id='second-submit-task',reason='submit',review_observation_id=snap['observation_id'],approval_ref='new-approval-reference'),w.INTERNAL_KEY)

@pytest.mark.asyncio
async def test_page_change_before_offer_rejected():
    async with portal() as (sid,ctx,p,info,posts):
        snap=await core.snapshot(sid,w.INTERNAL_KEY);await p.evaluate("document.querySelector('input').value='changed'")
        with pytest.raises(HTTPException) as error:await core.human_begin(sid,core.HumanBegin(task_id='stale-review-task',reason='submit',review_observation_id=snap['observation_id'],approval_ref='stale-approval'),w.INTERNAL_KEY)
        assert error.value.status_code==409 and not info.human_task_id

@pytest.mark.asyncio
async def test_idle_reaper_preserves_active_submit_lease(monkeypatch):
    async with portal() as (sid,ctx,p,info,posts):
        await begin(sid)
        monkeypatch.setattr('browser.general_routes.contexts',{ctx.id:ctx});monkeypatch.setattr(w,'sessions',{})
        monkeypatch.setenv('MAX_BROWSER_IDLE_SECONDS','1');ctx.last_used=time.time()-100
        count=0
        original_sleep=asyncio.sleep
        async def tick(delay):
            nonlocal count
            count+=1
            if count>1:raise asyncio.CancelledError()
        monkeypatch.setattr('browser.worker.asyncio.sleep',tick)
        try:
            with pytest.raises(asyncio.CancelledError):await w.reap_idle()
        finally:monkeypatch.setattr('browser.worker.asyncio.sleep',original_sleep)
        assert not p.is_closed()

@pytest.mark.asyncio
async def test_expiry_during_preflight_still_refuses_click(monkeypatch):
    from browser import human_submit
    async with portal() as (sid,ctx,p,info,posts):
        task,target,view=await begin(sid)
        original=human_submit.check_review;checks=0
        async def preflight(info,ctx):
            nonlocal checks
            result=await original(info,ctx);checks+=1
            if checks==2:info.human_expires=time.time()-1
            return result
        monkeypatch.setattr(human_submit,'check_review',preflight)
        with pytest.raises(HTTPException) as error:await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=target['ref'],observation_id=view['observation_id']),w.INTERNAL_KEY)
        assert error.value.status_code==403 and not posts and not info.consumed
