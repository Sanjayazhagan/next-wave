"""Record a real 2–3 minute silent synthetic local demo, not a deployed-system claim."""
import asyncio
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.test_harness import services


async def main():
    out=Path('output/demo');out.mkdir(parents=True,exist_ok=True)
    scenes=[];started=time.monotonic()
    async with services(out,8890,8891) as (base,env):
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            context=await browser.new_context(viewport={'width':1440,'height':1000},record_video_dir=str(out/'raw'),record_video_size={'width':1440,'height':1000})
            page=await context.new_page();page.set_default_timeout(30000)
            async def hold(name,seconds=12):
                scenes.append({'scene':name,'elapsed_seconds':round(time.monotonic()-started,1)})
                print(name,flush=True);await page.wait_for_timeout(seconds*1000)
            async def click(name):
                await page.wait_for_function('!busy');await page.get_by_role('button',name=name).click()
            await page.goto(base)
            await hold('Synthetic local operator console; no government application',12)
            await page.get_by_role('checkbox').check();await click('Start secure demo')
            await page.locator('#otp-val').wait_for();await hold('Citizen supplies fictional OTP',12)
            await page.locator('#otp-val').fill('246810');await click('Verify entered OTP')
            await page.locator('#human-val').wait_for();await hold('Workflow pauses for a human challenge',12)
            await click('Open focused human verification')
            link=page.get_by_role('link',name='Complete verification in the same browser')
            await link.wait_for();destination=await link.get_attribute('href')
            await page.goto(base+destination);await page.get_by_role('button',name='Open verification').click()
            await page.locator('#screen').wait_for(state='visible');await hold('Focused live challenge; same browser session',15)
            await page.get_by_label('Your answer',exact=True).fill('7');await page.get_by_role('button',name='Verify and continue').click()
            await page.locator('#done').wait_for(state='visible');await hold('Completion verified by the portal; no WhatsApp message sent',12)
            await page.goto(base);await page.get_by_role('button',name='Auto-fill and verify review').wait_for()
            await click('Rename a field');await click('Inject a popup');await click('Server error')
            await hold('Synthetic field drift, popup and transient error injected',15)
            await click('Auto-fill and verify review');await page.get_by_role('button',name='I approve').wait_for()
            await hold('Live review and explicit approval gate',15)
            await page.locator('#active-control input[name=income]').fill('130000');await click('Save edits and prepare fresh review')
            await page.get_by_role('button',name='Auto-fill and verify review').wait_for();await hold('Citizen edit invalidates the previous review',12)
            await click('Auto-fill and verify review');await page.get_by_role('button',name='I approve').wait_for();await hold('Fresh review before final approval',12)
            await click('I approve');await page.get_by_text('Receipt captured',exact=True).wait_for()
            await hold('Approved fictional receipt; not government-issued',15)
            await click('Check simulated application status');await hold('Observed mock status and audit evidence',12)
            video=page.video
            await context.close()
            await video.save_as(str(out/'civicflow-local-demo.webm'))
            await browser.close()
    (out/'scenes.json').write_text(json.dumps({'scope':'actual local synthetic demo, silent, no deployed/WhatsApp/real-portal claim','scenes':scenes},indent=2),encoding='utf-8')
    print('Recorded:',out/'civicflow-local-demo.webm',flush=True)


if __name__=='__main__':asyncio.run(main())
