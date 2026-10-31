"""Real DOM contract tests without real citizen credentials or external portals."""
import os
import secrets
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright

from browser import core_compat as core, worker as w
from browser.general import GeneralContext, observe, origin
from browser.general_routes import contexts
from browser.step_policy import category, final_path

HTML='''<!doctype html><html><head><title>Human challenge test</title></head><body>
<p>Login verification OTP</p><input id="code" aria-label="OTP Code">
<button type="button" onclick="document.querySelector('#sent').innerText='OTP requested'">Send OTP Code</button>
<button type="button" onclick="document.querySelector('#done').innerText='Code attempted'">Verify OTP</button>
<p id="sent"></p><p id="done"></p>
<input type="file" aria-label="Document" accept=".pdf">
<button type="button" onclick="document.querySelector('#upload').innerText='Document uploaded'">Upload Document</button>
<p id="upload"></p><button type="submit">Submit Application</button>
</body></html>'''


def test_categories_are_distinct():
    assert category({'tag':'button','label':'Send OTP Code','type':'button'},has_auth=True)=='otp_send'
    assert category({'tag':'button','label':'Resend verification code','type':'submit'},has_auth=True)=='otp_send'
    assert category({'tag':'button','label':'Verify OTP','type':'submit'},has_auth=True)=='otp_verify'
    assert category({'tag':'button','label':'Upload Document','type':'submit'},has_file=True)=='upload_step'
    assert category({'tag':'button','label':'Next','type':'submit'})=='intermediate'
    assert category({'tag':'button','label':'Save Draft','type':'submit'})=='intermediate'
    assert category({'tag':'button','label':'Submit Application','type':'submit'})=='final'
    assert category({'tag':'button','label':'Confirm Application','type':'button'})=='final'
    assert category({'tag':'button','label':'','type':'submit'})=='final_unknown'
    assert final_path('https://example.org/application/submit')
    assert not final_path('https://example.org/login/send-otp')


@pytest.mark.asyncio
async def test_human_task_on_actual_dom_pauses_agent_and_keeps_submit_guard():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        context=await browser.new_context()
        page=await context.new_page();await page.set_content(HTML)
        session=GeneralContext(context=context,page=page,allowed=set())
        session.permitted=lambda url:url=='about:blank'
        contexts[session.id]=session;sid=secrets.token_urlsafe(24)
        core.bridges[sid]=core.BridgeSession(session.id,'test')
        task='human-task-'+secrets.token_urlsafe(8)
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            assert any(n.get('action_category')=='otp_send' for n in snap['nodes'])
            assert any(n.get('action_category')=='upload_step' for n in snap['nodes'])
            with pytest.raises(HTTPException) as err:
                x=next(n for n in snap['nodes'] if n['name']=='Submit Application')
                await core.action(sid,core.CoreAction(type='click',target=core.Target(role=x['role'],name=x['name'])),w.INTERNAL_KEY)
            assert err.value.status_code==403
            assert (await core.human_begin(sid,core.HumanBegin(task_id=task,expires_at=time.time()+180),w.INTERNAL_KEY))['state']=='paused_for_human'
            with pytest.raises(HTTPException) as busy:
                await core.action(sid,core.CoreAction(type='wait',wait_ms=200),w.INTERNAL_KEY)
            assert busy.value.status_code==409
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            assert view['screenshot_base64'] and view['viewport']['width']>0
            otp=next(n for n in view['controls'] if n['category']=='human_input')
            sent=next(n for n in view['controls'] if n['category']=='otp_send')
            await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=sent['ref']),w.INTERNAL_KEY)
            assert await page.locator('#sent').inner_text()=='OTP requested'
            await core.human_act(sid,core.HumanAction(task_id=task,kind='fill',target_ref=otp['ref'],value='123456'),w.INTERNAL_KEY)
            assert await page.locator('#code').input_value()=='123456'
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            verify=next(n for n in view['controls'] if n['category']=='otp_verify')
            await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref=verify['ref']),w.INTERNAL_KEY)
            assert await page.locator('#done').inner_text()=='Code attempted'
            with pytest.raises(HTTPException) as blocked:
                await core.human_act(sid,core.HumanAction(task_id=task,kind='click',target_ref='frame-0-element-6'),w.INTERNAL_KEY)
            assert blocked.value.status_code==403
            with pytest.raises(HTTPException) as blocked2:
                await core.human_act(sid,core.HumanAction(task_id=task,kind='challenge_click',x=100,y=100),w.INTERNAL_KEY)
            assert blocked2.value.status_code==403
            completed=await core.human_finish(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            assert completed['state']=='resumed' and completed['verified'] is False
            await core.snapshot(sid,w.INTERNAL_KEY)
            res=await core.action(sid,core.CoreAction(type='wait',wait_ms=200),w.INTERNAL_KEY)
            assert res['ok']
        finally:
            await core.close(sid,w.INTERNAL_KEY);await browser.close()


@pytest.mark.asyncio
async def test_otp_request_is_bounded_even_if_agent_retries():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
        context=await browser.new_context();page=await context.new_page();await page.set_content(HTML)
        ctx=GeneralContext(context=context,page=page,allowed=set());ctx.permitted=lambda u:u=='about:blank'
        contexts[ctx.id]=ctx;sid=secrets.token_urlsafe(16)
        core.bridges[sid]=core.BridgeSession(ctx.id,'test')
        try:
            for _ in range(2):
                snap=await core.snapshot(sid,w.INTERNAL_KEY)
                node=next(n for n in snap['nodes'] if n['action_category']=='otp_send')
                r=await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
                assert r['requires_human_otp']
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            node=next(n for n in snap['nodes'] if n['action_category']=='otp_send')
            with pytest.raises(HTTPException) as exc:
                await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
            assert exc.value.status_code==429
        finally:
            await core.close(sid,w.INTERNAL_KEY);await browser.close()

@pytest.mark.asyncio
async def test_long_navigation_menu_does_not_hide_form_controls():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
        context=await browser.new_context();page=await context.new_page()
        await page.set_content('<html><body>'+''.join(f'<a href="/link{i}">Link {i}</a>' for i in range(320))+'<label>Income Certificate<input type="file" accept=".pdf"></label><label>Date<input type="text" name="date"></label></body></html>')
        ctx=GeneralContext(context=context,page=page,allowed=set());ctx.permitted=lambda u:u=='about:blank'
        obs=await observe(ctx)
        assert obs['truncated']
        assert any(e['type']=='file' for e in obs['elements'])
        assert any(e['name']=='date' for e in obs['elements'])
        await browser.close()


@pytest.mark.asyncio
async def test_post_write_policy_allows_only_scoped_auth_or_reviewed_intermediate(monkeypatch):
    from browser.general import trusted_captcha_provider
    assert trusted_captcha_provider('https://www.google.com/recaptcha/api2/reload')
    assert not trusted_captcha_provider('https://google.com.evil.example/recaptcha/api2/reload')
    assert not trusted_captcha_provider('http://www.google.com/recaptcha/api2/reload')
    class Route:
        def __init__(self,url,method):
            self.request=SimpleNamespace(method=method,url=url);self.disposition=None
        async def abort(self,reason):self.disposition='blocked';return self.disposition
        async def continue_(self):self.disposition='allowed';return self.disposition
    ctx=GeneralContext(context=None,page=None,allowed=set(),public_web=True)
    ctx.permitted=lambda url:True
    async def safe(*a):pass
    monkeypatch.setattr('browser.general.assert_public_url',safe)
    r=Route('https://example.org/login/otp/send','POST')
    await ctx.route(r);assert r.disposition=='blocked'
    ctx.write_scope=(origin('https://example.org/login'),'otp_send')
    r=Route('https://example.org/login/otp/send','POST')
    await ctx.route(r);assert r.disposition=='allowed'
    r=Route('https://evil.com/login/otp/send','POST')
    await ctx.route(r);assert r.disposition=='blocked'
    r=Route('https://example.org/application/submit','POST')
    await ctx.route(r);assert r.disposition=='blocked'
    ctx.write_scope=None;ctx.human_captcha_until=time.time()+60
    r=Route('https://www.google.com/recaptcha/api2/reload','POST')
    await ctx.route(r);assert r.disposition=='allowed'
    ctx.human_captcha_until=0
    r=Route('https://www.google.com/recaptcha/api2/reload','POST')
    await ctx.route(r);assert r.disposition=='blocked'
