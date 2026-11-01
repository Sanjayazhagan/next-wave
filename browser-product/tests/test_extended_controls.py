import asyncio
import json
import uuid
import pytest
from fastapi import HTTPException
from browser.general import observe,act
from browser.protocol import BrowserAction
from tests.test_navigation_compatibility import fixture

def command(obs,kind,e=None,**kw):
    return BrowserAction(action_id=str(uuid.uuid4()),observation_id=obs['observation_id'],kind=kind,target_ref=e['ref'] if e else None,verified=True,source_ref='citizen:test-input',**kw)

@pytest.mark.asyncio
async def test_custom_autocomplete_option_is_observed_and_selected():
    html='''<input aria-label="City" role="combobox" oninput="document.querySelector('[role=listbox]').hidden=false">
    <div role="listbox" hidden><div role="option" tabindex="0" onclick="document.querySelector('input').value='Mumbai';this.setAttribute('aria-selected','true')">Mumbai</div></div>'''
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);e=next(e for e in obs['elements'] if e['tag']=='input')
        result=await act(ctx,command(obs,'fill',e,value='Mum'),capture_screenshot=False)
        option=next(e for e in result['observation']['elements'] if e['role']=='option')
        result=await act(ctx,command(result['observation'],'click',option),capture_screenshot=False)
        assert await page.locator('input').input_value()=='Mumbai'
        assert result['effect']['matched'] is True

@pytest.mark.asyncio
async def test_modal_exposes_scoped_controls_and_prevents_background_click():
    html='''<button onclick="window.wrong=true">Background</button><dialog open style="position:fixed;inset:0;width:100vw;height:100vh;z-index:99"><h2>Choose city</h2><button onclick="this.closest('dialog').remove()">Close dialog</button></dialog>'''
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False)
        assert obs['interaction_state']['overlays']
        bg=next(e for e in obs['elements'] if e['label']=='Background')
        with pytest.raises(HTTPException):await act(ctx,command(obs,'click',bg),capture_screenshot=False)
        obs=await observe(ctx,screenshot=False);close=next(e for e in obs['elements'] if e['label']=='Close dialog')
        result=await act(ctx,command(obs,'click',close),capture_screenshot=False)
        assert not result['observation']['interaction_state']['overlays']
        assert not await page.evaluate('Boolean(window.wrong)')

@pytest.mark.asyncio
async def test_dates_multiselect_and_rerendered_fields_require_readback():
    html='''<label>Date<input type="date"></label><label>Topics<select multiple><option value="a">A</option><option value="b">B</option></select></label><button onclick="document.querySelector('input').outerHTML='<input type=date aria-label=Date>'">Next step</button>'''
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);date=next(e for e in obs['elements'] if e['type']=='date')
        result=await act(ctx,command(obs,'fill',date,value='2026-11-01'),capture_screenshot=False);assert result['effect']['matched']
        obs=result['observation'];select=next(e for e in obs['elements'] if e['tag']=='select')
        result=await act(ctx,command(obs,'select',select,values=['a','b']),capture_screenshot=False);assert result['effect']['matched']
        obs=result['observation'];button=next(e for e in obs['elements'] if e['label']=='Next step')
        result=await act(ctx,command(obs,'click',button),capture_screenshot=False)
        assert next(e for e in result['observation']['elements'] if e['type']=='date')['value']==''
        assert result['effect']['check']=='interaction_observation'

@pytest.mark.asyncio
@pytest.mark.parametrize('with_ids',[True,False])
async def test_duplicate_labels_cannot_retarget_after_reordering(with_ids):
    html='<button '+('id="a"' if with_ids else '')+' onclick="window.which=1">Choose</button><button '+('id="b"' if with_ids else '')+' onclick="window.which=2">Choose</button>'
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);first=obs['elements'][0]
        await page.evaluate("document.body.prepend(document.querySelectorAll('button')[1])")
        with pytest.raises(HTTPException) as error:await act(ctx,command(obs,'click',first),capture_screenshot=False)
        assert error.value.status_code==409
        assert not await page.evaluate('Boolean(window.which)')

@pytest.mark.asyncio
async def test_delayed_validation_is_not_declared_form_success():
    html='<input aria-label="Code"><button onclick="setTimeout(()=>document.querySelector(\'p\').innerText=\'Invalid code\',250)">Check value</button><p role="alert"></p>'
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);button=next(e for e in obs['elements'] if e['tag']=='button')
        result=await act(ctx,command(obs,'click',button),capture_screenshot=False)
        assert result['effect']['confirmed_by_portal'] is False
        await asyncio.sleep(.3);after=await observe(ctx,screenshot=False)
        assert 'Invalid code' in after['text']

@pytest.mark.asyncio
async def test_closed_session_is_explicit_not_auto_reopened():
    from browser import core_compat as core,worker
    async with fixture('<input aria-label="Name">') as (sid,ctx,page):
        await ctx.context.close()
        with pytest.raises(HTTPException) as error:await core.snapshot(sid,worker.INTERNAL_KEY)
        assert error.value.status_code in (404,410)

def test_search_policy_requires_structural_get_form_not_just_label():
    from browser.step_policy import category
    assert category({'tag':'button','type':'submit','label':'Search','form':True,'form_method':'get','form_search_only':True,'form_action':'https://www.google.com/search'})=='search'
    assert category({'tag':'button','type':'submit','label':'Search','form':True,'form_method':'post','form_search_only':False})=='final_unknown'
    assert category({'tag':'button','type':'submit','label':'Pay','form':True,'form_method':'get','form_search_only':True})=='final'

@pytest.mark.asyncio
async def test_reviewed_search_get_runs_without_final_approval_and_post_stays_blocked(monkeypatch):
    import os,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from playwright.async_api import async_playwright
    from browser.general import GeneralContext,origin
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path);self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<p>Search results for Mumbai</p>' if self.path.startswith('/search?') else b'<form action="/search" method="get"><input name="q" aria-label="Search" value="Mumbai"><button>Search</button></form>')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('BROWSER_SEARCH_TARGETS_JSON',json.dumps([base+'/search']))
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','false')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(**({'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}))
        context=await browser.new_context();page=await context.new_page();ctx=GeneralContext(context=context,page=page,allowed={origin(base)})
        await context.route('**/*',ctx.route)
        try:
            await page.goto(base);obs=await observe(ctx,screenshot=False);button=next(e for e in obs['elements'] if e['tag']=='button')
            assert button['category']=='search'
            result=await act(ctx,command(obs,'click',button),capture_screenshot=False)
            assert result['effect']['url_changed'] and 'Search results' in result['observation']['text']
            assert len([r for r in requests if r.startswith('/search?')])==1
            assert ctx.native_submit_scope is None
        finally:await browser.close();server.shutdown();server.server_close()

@pytest.mark.asyncio
async def test_popup_and_download_are_distinct_from_submission_success():
    from browser.general import bound_tabs
    html='''<button onclick="window.open('about:blank')">Open help</button><button onclick="let a=document.createElement('a');a.href='/file';a.download='fixture.txt';a.click()">Get document</button>'''
    async with fixture(html) as (_,ctx,page):
        async def serve(route):
            if route.request.url.endswith('/file'):await route.fulfill(body='fixture',headers={'Content-Type':'text/plain','Content-Disposition':'attachment; filename="fixture.txt"'})
            else:await route.fulfill(body=html,content_type='text/html')
        await page.route('https://download.example/**',serve)
        ctx.permitted=lambda url:url=='about:blank' or url.startswith('https://download.example/')
        await page.goto('https://download.example/')
        bound_tabs(ctx)
        obs=await observe(ctx,screenshot=False);button=next(e for e in obs['elements'] if e['label']=='Open help')
        result=await act(ctx,command(obs,'click',button),capture_screenshot=False)
        assert result['effect']['new_tabs'] and not result['effect']['confirmed_by_portal']
        obs=result['observation'];button=next(e for e in obs['elements'] if e['label']=='Get document')
        async with page.expect_download(timeout=3000):
            result=await act(ctx,command(obs,'click',button),capture_screenshot=False)
        assert ctx.download_events==1
        assert (await observe(ctx,screenshot=False))['downloads_started_total']==1
        assert not result['effect']['confirmed_by_portal']

@pytest.mark.asyncio
async def test_custom_calendar_cell_and_option_need_verified_source():
    html='''<input aria-label="Date" readonly><div role="gridcell" tabindex="0" onclick="document.querySelector('input').value='2026-11-01'">1 November 2026</div>'''
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);cell=next(e for e in obs['elements'] if e['role']=='gridcell')
        with pytest.raises(HTTPException):await act(ctx,command(obs,'click',cell).model_copy(update={'verified':False}),capture_screenshot=False)
        result=await act(ctx,command(obs,'click',cell),capture_screenshot=False)
        assert next(e for e in result['observation']['elements'] if e['tag']=='input')['value']=='2026-11-01'

@pytest.mark.asyncio
async def test_bounded_backoff_and_unknown_network_write_not_replayed(monkeypatch):
    import httpx
    from clients.general_browser import GeneralBrowserClient
    from clients.reliability import request_with_backoff
    delays=[];calls=[]
    async def sleep(delay):delays.append(delay)
    monkeypatch.setattr('clients.reliability.asyncio.sleep',sleep)
    def busy(req):
        calls.append(req)
        return httpx.Response(429,json={'detail':'busy'},headers={'Retry-After':'1','X-Browser-Outcome':'not_applied'}) if len(calls)<3 else httpx.Response(200,json={'ok':True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(busy),base_url='http://local') as http:
        assert (await request_with_backoff(http,'POST','/create',{}))['ok']
        assert len(calls)==3 and delays==[1,1]
    calls.clear()
    def unknown(req):calls.append(req);raise httpx.ReadTimeout('lost response',request=req)
    client=GeneralBrowserClient('http://local','fixture');await client.http.aclose();client.http=httpx.AsyncClient(base_url='http://local',transport=httpx.MockTransport(unknown))
    async with client:
        action=BrowserAction(action_id='lost-write-action',observation_id='fixture',kind='click',target_ref='button')
        with pytest.raises(httpx.ReadTimeout):await client.act('session',action)
        with pytest.raises(RuntimeError):await client.act('session',action.model_copy(update={'action_id':'new-unsafe-action'}))
        assert len(calls)==1

@pytest.mark.asyncio
async def test_multistep_form_reset_clears_attachment_in_observation():
    html='<form><label>File<input type="file"></label><button type="reset">Clear step</button></form>'
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);upload=next(e for e in obs['elements'] if e['type']=='file')
        result=await act(ctx,command(obs,'upload',upload),upload={'name':'fixture.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4 fixture'},capture_screenshot=False)
        assert next(e for e in result['observation']['elements'] if e['type']=='file')['file_count']==1
        obs=result['observation'];reset=next(e for e in obs['elements'] if e['label']=='Clear step')
        result=await act(ctx,command(obs,'click',reset),capture_screenshot=False)
        assert next(e for e in result['observation']['elements'] if e['type']=='file')['file_count']==0

@pytest.mark.asyncio
async def test_core_pauses_expired_session_without_requesting_a_decision():
    import httpx
    from clients.core_browser import CoreBrowserClient
    def handler(req):return httpx.Response(200,json={'session_expired':True})
    async def decide(obs):raise AssertionError('expired session must not execute a model action')
    async with CoreBrowserClient('http://local','fixture',transport=httpx.MockTransport(handler)) as client:
        assert (await client.step('expired',decide))['requires_reauthentication']

@pytest.mark.asyncio
async def test_same_name_same_size_file_replacement_invalidates_approval(monkeypatch):
    from browser import core_compat as core,worker
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','true')
    async with fixture('<form><input type="file"><button>Submit</button></form>') as (sid,ctx,page):
        await page.locator('input').set_input_files({'name':'fixture.pdf','mimeType':'application/pdf','buffer':b'AAAA'})
        snap=await core.snapshot(sid,worker.INTERNAL_KEY)
        await core.authorize(sid,core.Authorization(approved=True,approval_ref='citizen-file-review',review_observation_id=snap['observation_id']),worker.INTERNAL_KEY)
        await page.locator('input').set_input_files({'name':'fixture.pdf','mimeType':'application/pdf','buffer':b'BBBB'})
        with pytest.raises(HTTPException) as error:
            await core.action(sid,core.CoreAction(type='click',action_id='changed-file-submit',target=core.Target(role='button',name='Submit')),worker.INTERNAL_KEY)
        assert error.value.status_code==409
