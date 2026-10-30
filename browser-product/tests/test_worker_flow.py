"""Worker logic with live Chromium + in-memory HTML; no networking required.
Covers actual worker fill, semantic drift, transient failure, approval proof and receipt.
"""
import base64, hashlib, hmac, json, time
from pathlib import Path
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
import browser.worker as w
from server.app import fixture_pdf
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.asyncio
async def test_worker_flow_gate_and_fake_receipt():
    async with async_playwright() as pw:
        b=await pw.chromium.launch(**({'executable_path':'/usr/bin/chromium'} if Path('/usr/bin/chromium').exists() else {}),headless=True,args=['--no-sandbox'])
        ctx=await b.new_context()
        page=await ctx.new_page()
        # Some managed Chromium images deny storage at the about:blank origin.
        await page.evaluate("""()=>{const d={};Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}})}""")
        await page.set_content((ROOT/'web'/'mock.html').read_text(encoding='utf-8'),wait_until='domcontentloaded')
        # Intercept mock API via a fetch stub rather than a real network URL.
        await page.evaluate("""()=>{window.fetch=async ()=>({ok:true,json:async()=>({receipt_id:'MOCK-2026-TESTRECEIPT'})})}""")
        await page.get_by_role('button',name='Send login OTP').click()
        sid='test-worker-flow'; w.sessions[sid]=w.Session(context=ctx,page=page)
        try:
            assert (await w.otp(sid,w.OtpRequest(otp='000000'),w.INTERNAL_KEY))['ok'] is False
            assert (await w.otp(sid,w.OtpRequest(otp='246810'),w.INTERNAL_KEY))['stage']=='captcha_needed'
            assert (await w.human(sid,w.HumanRequest(challenge_answer='7'),w.INTERNAL_KEY))['stage']=='form_ready'
            await w.inject(sid,w.InjectRequest(script_name='rename_income'),w.INTERNAL_KEY)
            await w.inject(sid,w.InjectRequest(script_name='popup'),w.INTERNAL_KEY)
            await w.inject(sid,w.InjectRequest(script_name='server_failure'),w.INTERNAL_KEY)
            profile={'student_name':'Synthetic Student','course':'B.Tech','income':'120000','state':'Tamil Nadu','category':'BC'}
            result=await w.fill(sid,w.FillRequest(profile=profile,file_base64=base64.b64encode(fixture_pdf()).decode()),w.INTERNAL_KEY)
            assert result['stage']=='review_ready',result
            assert any(x['method']=='semantic-repair' for x in result['fields'])
            assert result['actual']==profile
            digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            with pytest.raises(HTTPException) as exc:
                await w.submit(sid,w.SubmitRequest(capability='0.bad',review_hash=digest),w.INTERNAL_KEY)
            assert exc.value.status_code==403
            expires=int(time.time())+40
            cap=f'{expires}.{w.expected_cap(sid,digest,expires)}'
            result=await w.submit(sid,w.SubmitRequest(capability=cap,review_hash=digest),w.INTERNAL_KEY)
            assert result['stage']=='submitted'
            assert result['receipt']=='MOCK-2026-TESTRECEIPT'
            again=await w.submit(sid,w.SubmitRequest(capability=cap,review_hash=digest),w.INTERNAL_KEY)
            assert again['already_submitted'] is True
        finally:
            w.sessions.pop(sid,None)
            await ctx.close();await b.close()

@pytest.mark.asyncio
async def test_worker_expired_login_and_three_real_failed_repairs():
    async with async_playwright() as pw:
        b=await pw.chromium.launch(**({'executable_path':'/usr/bin/chromium'} if Path('/usr/bin/chromium').exists() else {}),headless=True,args=['--no-sandbox'])
        ctx=await b.new_context();page=await ctx.new_page()
        await page.evaluate("""()=>{const d={};Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}})}""")
        await page.set_content((ROOT/'web'/'mock.html').read_text(encoding='utf-8'))
        await page.get_by_role('button',name='Send login OTP').click()
        sid='test-expiry';w.sessions[sid]=w.Session(context=ctx,page=page)
        try:
            await w.otp(sid,w.OtpRequest(otp='246810'),w.INTERNAL_KEY)
            await w.human(sid,w.HumanRequest(challenge_answer='7'),w.INTERNAL_KEY)
            expired=await w.inject(sid,w.InjectRequest(script_name='expire_session'),w.INTERNAL_KEY)
            assert expired['stage']=='otp'
            await w.otp(sid,w.OtpRequest(otp='246810'),w.INTERNAL_KEY)
            await w.human(sid,w.HumanRequest(challenge_answer='7'),w.INTERNAL_KEY)
            await w.inject(sid,w.InjectRequest(script_name='hide_income'),w.INTERNAL_KEY)
            profile={'student_name':'Synthetic','course':'B.Tech','income':'120000','state':'Tamil Nadu','category':'BC'}
            result=await w.fill(sid,w.FillRequest(profile=profile),w.INTERNAL_KEY)
            assert result['stage']=='human_takeover'
            assert result['repair_attempts']==3
            assert result['blocked_field']=='income'
            assert await w.page_phase(page)=='form'
        finally:
            w.sessions.pop(sid,None)
            await ctx.close();await b.close()
