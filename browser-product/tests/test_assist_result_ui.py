import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import pytest
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[1]

@asynccontextmanager
async def ui(result,*,late_refresh=False,error=False,reason='submit',late_view_error=False):
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(**({'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}))
        page=await browser.new_page();counts={'views':0,'posts':0}
        async def handle(route):
            path=urlsplit(route.request.url).path
            if path.endswith('/view'):
                counts['views']+=1
                if late_refresh and counts['views']>1:
                    await asyncio.sleep(.5)
                    if late_view_error:
                        await route.fulfill(status=403,json={'detail':'Old view expired'});return
                await route.fulfill(json={'reason':reason,'expires_at':time.time()+600,'observation_id':'view-id','url':'https://practice.example/form','viewport':{'width':1180,'height':760},'challenge_boxes':[],'screenshot_base64':'','controls':[{'ref':'submit-ref','label':'Submit Application','category':'final_submit','type':'submit'}] if reason=='submit' else []})
            elif path.endswith('/control') or path.endswith('/complete'):
                counts['posts']+=1
                await route.fulfill(status=409 if error else 200,json={'detail':'Review page changed; new review required'} if error else result)
            elif path=='/core-assist.js':await route.fulfill(body=(ROOT/'web/core_assist.js').read_text(),content_type='application/javascript')
            elif path=='/core-assist.css':await route.fulfill(body=(ROOT/'web/core_assist.css').read_text(),content_type='text/css')
            else:await route.fulfill(body=(ROOT/'web/core_assist.html').read_text(),content_type='text/html',headers={'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; connect-src 'self'"})
        await page.route('https://ui.example/**',handle);await page.goto('https://ui.example/core-assist/demo-task#private-fixture-token')
        await expect(page.locator('#expiry')).to_contain_text('expires')
        try:yield page,counts
        finally:await browser.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('result,status,phrase',[
 ({'state':'completed','confirmed_by_portal':True,'receipt_number':'DEMO-SCH-123'},'Submission confirmed','Receipt: DEMO-SCH-123'),
 ({'state':'completed','confirmed_by_portal':True,'receipt_number':None},'Submission confirmed','No receipt number was provided'),
 ({'state':'uncertain','confirmed_by_portal':False},'Submission outcome uncertain','portal has not confirmed'),
 ({'state':'review_changed','confirmed_by_portal':False},'New review required','reviewed page changed')])
async def test_terminal_result_clears_timer_and_uses_actual_confirmation(result,status,phrase):
    async with ui(result) as (page,counts):
        await page.get_by_role('button',name='Click Submit Application').click()
        await expect(page.locator('#status')).to_have_text(status)
        assert phrase in await page.locator('#message').inner_text()
        assert await page.locator('#expiry').inner_text()=='' and not await page.locator('#expiry').is_visible()
        assert await page.locator('#refresh').is_disabled() and counts['posts']==1
        assert not await page.locator('#screen-wrap').is_visible()

@pytest.mark.asyncio
@pytest.mark.parametrize('late_error',[False,True])
async def test_late_view_cannot_restore_old_countdown_or_controls(late_error):
    async with ui({'state':'completed','confirmed_by_portal':True,'receipt_number':'DEMO-SCH-123'},late_refresh=True,late_view_error=late_error) as (page,counts):
        await page.locator('#refresh').click();await page.get_by_role('button',name='Click Submit Application').click()
        await asyncio.sleep(.7)
        assert await page.locator('#status').inner_text()=='Submission confirmed'
        assert await page.locator('#expiry').inner_text()=='' and not await page.locator('#expiry').is_visible()
        assert await page.locator('#controls button').count()==0
        assert 'Receipt: DEMO-SCH-123' in await page.locator('#message').inner_text()

@pytest.mark.asyncio
async def test_error_also_clears_countdown_without_claiming_failure_or_success():
    async with ui({},error=True) as (page,counts):
        await page.get_by_role('button',name='Click Submit Application').click()
        await expect(page.locator('#status')).to_have_text('Check submission with the bot')
        assert not await page.locator('#expiry').is_visible() and await page.locator('#expiry').inner_text()==''

@pytest.mark.asyncio
async def test_ordinary_handoff_completion_clears_timer_too():
    async with ui({'still_waiting_human':False},reason='captcha') as (page,counts):
        await page.locator('#done').click();await expect(page.locator('#status')).to_have_text('Handed back to agent')
        assert not await page.locator('#expiry').is_visible() and await page.locator('#expiry').inner_text()==''
