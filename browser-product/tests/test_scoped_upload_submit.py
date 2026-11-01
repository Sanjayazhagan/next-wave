"""Regression: a dedicated file upload can use a button named `submit`.

No external portal, credentials, language model, or government submission.
"""
import base64
import os
import secrets

import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright

from browser import core_compat as core, worker as w
from browser.general import GeneralContext, origin
from browser.general_routes import contexts
from browser.step_policy import category

PAGE = '''<!doctype html><html><head><title>Document portal</title></head><body>
<h1>Secure document upload</h1>
<form action="/upload" method="POST" enctype="multipart/form-data">
  <label for="doc">Certificate PDF</label>
  <input type="file" id="doc" name="certificate" accept=".pdf" required>
  <button type="submit">submit</button>
</form>
<form action="/application/submit" method="POST">
  <label for="applicant">Applicant</label><input id="applicant" name="applicant">
  <button type="submit">Submit Application</button>
</form></body></html>'''


@pytest.mark.asyncio
async def test_plain_submit_on_dedicated_upload_form_does_not_need_final_approval(monkeypatch):
    monkeypatch.delenv('BROWSER_INTERMEDIATE_POST_ORIGINS', raising=False)
    monkeypatch.setenv('BROWSER_ALLOW_FORM_POST', 'false')
    # Browser network access is restricted in this test runner. A real DOM
    # form submits to an absolute upload URL, but a local submit handler avoids
    # sending a network POST. The separate route test checks the POST policy.
    html=PAGE.replace('action="/upload"', 'action="https://upload.test/upload" onsubmit="event.preventDefault();document.body.innerHTML=\'<h1>Document upload successful</h1>\'"')
    html=html.replace('action="/application/submit"','action="https://upload.test/application/submit"')

    class PageURL:
        """Give an about:blank DOM a mock URL for local policy testing."""
        def __init__(self,page):self._page=page
        @property
        def url(self):return 'https://upload.test/secure'
        def __getattr__(self,key):return getattr(self._page,key)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        browser_context=await browser.new_context()
        page=await browser_context.new_page()
        await page.set_content(html)
        session=GeneralContext(context=browser_context,page=PageURL(page),allowed={origin('https://upload.test/secure')})
        contexts[session.id]=session
        sid=secrets.token_urlsafe(20)
        core.bridges[sid]=core.BridgeSession(session.id,'local')
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            doc=next(n for n in snap['nodes'] if n['role']=='fileupload')
            plain=next(n for n in snap['nodes'] if n['name']=='submit')
            final=next(n for n in snap['nodes'] if n['name']=='Submit Application')
            assert plain['action_category']=='upload_step'
            assert final['action_category']=='final'

            with pytest.raises(HTTPException) as no_file:
                await core.action(sid,core.CoreAction(type='click',target=core.Target(role=plain['role'],name=plain['name'])),w.INTERNAL_KEY)
            assert no_file.value.status_code==409
            assert 'Document portal' in await page.content()

            pdf=b'%PDF-1.4\n%%EOF'
            result=await core.action(sid,core.CoreAction(type='upload',target=core.Target(role=doc['role'],name=doc['name']),file_base64=base64.b64encode(pdf).decode(),file_name='certificate.pdf',file_mime='application/pdf'),w.INTERNAL_KEY)
            assert result['ok']
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            plain=next(n for n in snap['nodes'] if n['name']=='submit')
            clicked=await core.action(sid,core.CoreAction(type='click',target=core.Target(role=plain['role'],name=plain['name'])),w.INTERNAL_KEY)
            assert clicked['ok']
            assert clicked['kind']=='document_upload_step'
            assert clicked['confirmed_by_portal'] is False  # must inspect the page!
            assert 'Document upload successful' in (await core.snapshot(sid,w.INTERNAL_KEY))['page_text']
        finally:
            await core.close(sid,w.INTERNAL_KEY)
            await browser.close()


def test_submit_classification_stays_fail_closed_on_other_forms():
    assert category({'tag':'button','label':'submit','type':'submit','form_has_file':False,'form_upload_only':False,'form_action':'https://example.org/submit'},has_file=True)=='final'
    assert category({'tag':'button','label':'Submit Application','type':'submit','form_has_file':True,'form_upload_only':False,'form_action':'https://example.org/application/submit'},has_file=True)=='final'
    assert category({'tag':'button','label':'Submit','type':'submit','form_has_file':True,'form_upload_only':False,'form_action':'https://example.org/secure'},has_file=True)=='final'


@pytest.mark.asyncio
async def test_number_code_input_challenge_and_captcha_image_identification():
    html='''<h1>Verify OTP</h1><label>Code<input type="number" aria-label="Code"></label>
    <button type="button">Verify OTP</button><img width="140" height="40" src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" alt="Security code image">
    <button type="button">Refresh CAPTCHA</button>'''
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True, executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        context=await browser.new_context();page=await context.new_page();await page.set_content(html)
        session=GeneralContext(context=context,page=page,allowed=set())
        session.permitted=lambda url:url=='about:blank'
        contexts[session.id]=session
        sid=secrets.token_urlsafe(20)
        core.bridges[sid]=core.BridgeSession(session.id,'local')
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            code=next(n for n in snap['nodes'] if n['name']=='Code')
            assert code['role']=='spinbutton'
            assert code['action_category']=='human_input'
            assert snap['challenge']['kind']=='otp'
            assert snap['challenge']['input']['role']=='spinbutton'
            refresh=next(n for n in snap['nodes'] if n['name']=='Refresh CAPTCHA')
            assert refresh['action_category']=='captcha_refresh'
            task='human-test-'+secrets.token_urlsafe(8)
            import time
            await core.human_begin(sid,core.HumanBegin(task_id=task,expires_at=time.time()+120),w.INTERNAL_KEY)
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            assert any(c['category']=='captcha_refresh' for c in view['controls'])
            assert view['challenge_boxes'], 'Human CAPTCHA image region should be exposed'
            await core.human_cancel(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
        finally:
            await core.close(sid,w.INTERNAL_KEY);await browser.close()


@pytest.mark.asyncio
async def test_document_post_permission_is_exact_target_and_single_click(monkeypatch):
    from types import SimpleNamespace
    from browser.general import safe_url
    monkeypatch.delenv('BROWSER_INTERMEDIATE_POST_ORIGINS', raising=False)
    monkeypatch.setenv('BROWSER_ALLOW_FORM_POST','false')

    class Route:
        def __init__(self,url,method='POST'):
            self.request=SimpleNamespace(url=url,method=method)
            self.decision=None
        async def abort(self,*_):self.decision='blocked'
        async def continue_(self):self.decision='allowed'

    context=GeneralContext(context=None,page=None,allowed={origin('https://upload.test/secure')})
    context.write_scope=(origin('https://upload.test/secure'),'upload_form','https://upload.test/upload')
    for url,method,expected in [
        ('https://upload.test/upload','POST','allowed'),
        ('https://upload.test/upload?session=abc','POST','allowed'),
        ('https://upload.test/upload-other','POST','blocked'),
        ('https://upload.test/application/submit','POST','blocked'),
        ('https://upload.test/upload','PATCH','blocked'),
        ('https://attacker.test/upload','POST','blocked'),
        ('https://upload.test/upload?final_submit=true','POST','blocked'),
    ]:
        context.write_scope=(origin('https://upload.test/secure'),'upload_form','https://upload.test/upload')
        req=Route(url,method)
        await context.route(req)
        assert req.decision==expected,(url,method,req.decision)
    context.write_scope=None
    req=Route('https://upload.test/upload')
    await context.route(req)
    assert req.decision=='blocked'
