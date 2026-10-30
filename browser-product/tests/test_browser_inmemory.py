"""Use an in-memory mock page to test Playwright locators, without network access.
On the verification host Chromium's enterprise URLBlocklist blocks all URLs, so this
checks DOM interactions but is NOT a substitute for Docker full integration tests.
"""
from pathlib import Path
import pytest
from playwright.async_api import async_playwright
from browser.worker import Session, fill_field, page_phase
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.asyncio
async def test_mock_dom_human_steps_and_semantic_repair():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(**({'executable_path':'/usr/bin/chromium'} if Path('/usr/bin/chromium').exists() else {}),headless=True,args=['--no-sandbox'])
        page=await browser.new_page()
        # Replace sessionStorage on about:blank (storage access denied on opaque origin).
        await page.evaluate("""()=>{const d={};Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}})}""")
        await page.set_content((ROOT/'web'/'mock.html').read_text(encoding='utf-8'),wait_until='domcontentloaded')
        assert await page_phase(page)=='login'
        await page.get_by_role('button',name='Send login OTP').click()
        assert await page_phase(page)=='otp'
        await page.get_by_label('One-time code').fill('246810')
        await page.get_by_role('button',name='Verify OTP').click()
        assert await page_phase(page)=='challenge'
        await page.get_by_label('Human challenge answer').fill('7')
        await page.get_by_role('button',name='Continue as human').click()
        assert await page_phase(page)=='form'
        await page.evaluate('window.demoInject("rename_income")')
        s=Session(context=None,page=page)
        kind=await fill_field(s,'Annual family income','Household annual earnings','120000','income')
        assert kind=='semantic-repair'
        assert s.repairs==1
        assert await page.get_by_label('Household annual earnings').input_value()=='120000'
        await page.evaluate('window.demoInject("popup")')
        assert await page.get_by_role('button',name='Dismiss notice').count()==1
        await page.get_by_role('button',name='Dismiss notice').click()
        await page.evaluate('window.demoInject("server_failure")')
        await page.get_by_label('Student name').fill('Synthetic Tester')
        await page.get_by_label('Course').fill('B.Tech')
        await page.get_by_label('State').fill('Tamil Nadu')
        await page.get_by_label('Community category').fill('BC')
        await page.get_by_label('Household annual earnings').fill('120000')
        await page.get_by_role('button',name='Continue to review').click()
        assert await page_phase(page)=='form'
        await page.get_by_role('button',name='Continue to review').click()
        assert await page_phase(page)=='review'
        actual=await page.evaluate('window.demoReviewData()')
        assert actual['student_name']=='Synthetic Tester'
        assert actual['income']=='120000'
        await browser.close()
