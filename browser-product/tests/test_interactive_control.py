from pathlib import Path
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
import browser.worker as w


@pytest.mark.asyncio
async def test_direct_control_stale_frames_and_stage_boundary():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.evaluate("""()=>{const d={};Object.defineProperty(window,'sessionStorage',{value:{getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v)}})}""")
        await page.set_content((Path(__file__).resolve().parents[1]/'web'/'mock.html').read_text(encoding='utf-8'))
        await page.get_by_role('button',name='Send login OTP').click()
        sid = 'interactive-test'
        w.sessions[sid] = w.Session(context=ctx,page=page)
        try:
            await w.otp(sid,w.OtpRequest(otp='246810'),w.INTERNAL_KEY)
            async def click(locator):
                frame = await w.challenge_view(sid,w.INTERNAL_KEY)
                root = await page.locator('#main').bounding_box()
                box = await locator.bounding_box()
                return await w.human_control(sid,w.HumanControl(kind='click',frame_id=frame['frame_id'],x=(box['x']+box['width']/2-root['x'])/root['width'],y=(box['y']+box['height']/2-root['y'])/root['height']),w.INTERNAL_KEY)
            await click(page.get_by_label('Human challenge answer'))
            frame = await w.challenge_view(sid,w.INTERNAL_KEY)
            await w.human_control(sid,w.HumanControl(kind='text',frame_id=frame['frame_id'],text='7'),w.INTERNAL_KEY)
            with pytest.raises(HTTPException):
                await w.human_control(sid,w.HumanControl(kind='key',frame_id=frame['frame_id'],key='Enter'),w.INTERNAL_KEY)
            result = await click(page.get_by_role('button',name='Continue as human'))
            assert result['completed']
            with pytest.raises(HTTPException):
                await w.human_control(sid,w.HumanControl(kind='click',frame_id='fake'),w.INTERNAL_KEY)
        finally:
            w.sessions.pop(sid,None)
            await ctx.close();await b.close()
