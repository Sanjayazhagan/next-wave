"""Check bridge semantics and reviewed POST policy, no real citizen accounts."""
import base64
import os
import secrets
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright

from browser import core_compat as core, worker as w
from browser.general import GeneralContext, intermediate_post_permitted, observe
from browser.general_routes import contexts

HTML = '''<!doctype html><html><head><title>Upload Page</title></head><body>
<form><label for="document">Income certificate</label>
<div><label for="document">Income certificate</label><p>PDF or PNG, maximum 200 KB</p><input id="document" name="income_certificate" type="file" accept=".pdf,image/png" required></div>
<label for="person">Student</label><input id="person" type="text">
<button type="button">Next</button>
<button type="submit">Submit application</button>
</form></body></html>'''

@pytest.mark.asyncio
async def test_core_bridge_exposes_upload_rules_and_executes_document(monkeypatch):
    async with async_playwright() as pw:
        b=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx=await b.new_context(); page=await ctx.new_page(); await page.set_content(HTML)
        session=GeneralContext(context=ctx,page=page,allowed=set())
        session.permitted=lambda url:url=='about:blank'
        contexts[session.id]=session;sid=secrets.token_urlsafe(16)
        core.bridges[sid]=core.BridgeSession(context_id=session.id,portal_id='local')
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            doc=next(x for x in snap['nodes'] if x['role']=='fileupload')
            assert 'accepts: .pdf,image/png' in doc['name']
            assert '200 KB' in doc['name']
            assert doc['element_type']=='file'
            assert doc['accept']=='.pdf,image/png'
            assert doc['required'] is True
            assert 'PDF or PNG' in doc['upload_hint']
            assert snap['page_text']
            text=next(x for x in snap['nodes'] if x['name']=='Student')
            assert text['role']=='textbox'
            with pytest.raises(HTTPException) as err:
                await core.action(sid,core.CoreAction(type='upload',target=core.Target(role=text['role'],name=text['name']),file_name='income.pdf',file_mime='application/pdf',file_base64=base64.b64encode(b'%PDF-1.4\n%%EOF').decode()),w.INTERNAL_KEY)
            assert err.value.status_code==422
            doc=next(x for x in (await core.snapshot(sid,w.INTERNAL_KEY))['nodes'] if x['role']=='fileupload')
            res=await core.action(sid,core.CoreAction(type='upload',target=core.Target(role=doc['role'],name=doc['name']),file_name='income.pdf',file_mime='application/pdf',file_base64=base64.b64encode(b'%PDF-1.4\n%%EOF').decode()),w.INTERNAL_KEY)
            assert res['ok']
            assert await page.locator('input[type=file]').evaluate('e=>e.files.length')==1
        finally:
            await core.close(sid,w.INTERNAL_KEY);await b.close()

def test_intermediate_posts_are_explicit_per_origin(monkeypatch):
    monkeypatch.delenv('BROWSER_INTERMEDIATE_POST_ORIGINS',raising=False)
    monkeypatch.setenv('BROWSER_ALLOW_FORM_POST','true')
    assert not intermediate_post_permitted('https://selenium.dev/form',public_web=True)
    assert intermediate_post_permitted('https://selenium.dev/form',public_web=False)
    monkeypatch.setenv('BROWSER_INTERMEDIATE_POST_ORIGINS','https://testpages.eviltester.com')
    assert intermediate_post_permitted('https://testpages.eviltester.com/next',public_web=True)
    assert not intermediate_post_permitted('https://eviltester.com/next',public_web=True)
    assert not intermediate_post_permitted('https://testpages.eviltester.com.evil.com/next',public_web=True)
