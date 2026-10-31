"""Real Chromium DOM actions without network access; never fakes a portal run."""
import os
import secrets
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
from browser import worker as w, core_compat as core
from browser.general import GeneralContext
from browser.general_routes import contexts

HTML='''<html><head><title>Demo DOM</title></head><body>
<button type="button" onclick="document.getElementById('form').hidden=false">Open application</button>
<div id="form" hidden><label for="person">Student Name</label><input id="person">
<button type="button" onclick="document.getElementById('review').hidden=false">Next</button>
<div id="review" hidden><button type="submit" onclick="document.getElementById('done').hidden=false">Submit application</button></div>
<p id="done" hidden>Successfully submitted application. Application received: REF-DEMO-123</p>
</div></body></html>'''

@pytest.mark.asyncio
async def test_browser_actions_are_model_grounded_and_approval_gated(monkeypatch):
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','true')
    async with async_playwright() as pw:
        b=await pw.chromium.launch(headless=True,executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
        ctx=await b.new_context();page=await ctx.new_page();await page.set_content(HTML)
        session=GeneralContext(context=ctx,page=page,allowed=set())
        # This test never accesses network or real websites, so about:blank is a
        # permitted document in this fixture only.
        session.permitted=lambda url: url=='about:blank'
        ctx_id=session.id;sid=secrets.token_urlsafe(20)
        contexts[ctx_id]=session
        core.bridges[sid]=core.BridgeSession(ctx_id,'local',receipt_pattern='Application received: (REF-DEMO-[0-9]+)')
        try:
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            async def click(label):
                nonlocal snap
                node=next(x for x in snap['nodes'] if x['name']==label)
                await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
                snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await click('Open application')
            field=next(x for x in snap['nodes'] if x['name']=='Student Name')
            await core.action(sid,core.CoreAction(type='type',target=core.Target(role=field['role'],name=field['name']),value='Test Person'),w.INTERNAL_KEY)
            assert await page.locator('#person').input_value()=='Test Person'
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            await click('Next')
            # Stale decisions after an external DOM change cannot be applied.
            await page.evaluate('document.querySelector("#review").insertAdjacentText("beforeend","Review changed")')
            with pytest.raises(HTTPException) as stale:
                await click('Submit application')
            assert stale.value.status_code==409
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            with pytest.raises(HTTPException) as denied:
                await click('Submit application')
            assert denied.value.status_code==403
            assert (await core.snapshot(sid,w.INTERNAL_KEY))['receipt_number'] is None
            snap=await core.snapshot(sid,w.INTERNAL_KEY)
            with pytest.raises(HTTPException):
                await core.authorize(sid,core.Authorization(approved=True,approval_ref='core-human-approval',review_observation_id='stale-observation'),w.INTERNAL_KEY)
            await core.authorize(sid,core.Authorization(approved=True,approval_ref='core-human-approval',review_observation_id=snap['observation_id']),w.INTERNAL_KEY)
            with pytest.raises(HTTPException):
                await core.authorize(sid,core.Authorization(approved=True,approval_ref='core-human-approval',review_observation_id=snap['observation_id']),w.INTERNAL_KEY)
            await click('Submit application')
            assert snap['receipt_number']=='REF-DEMO-123'
            with pytest.raises(HTTPException):await click('Submit application')
        finally:
            await core.close(sid,w.INTERNAL_KEY);await b.close()
