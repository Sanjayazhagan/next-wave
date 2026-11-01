"""Full mock scholarship → approved human Submit → real practice receipt UI."""
import asyncio,json,os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from playwright.async_api import async_playwright,expect
from scripts.test_harness import services
from server.practice_scholarship import RECEIPT_PATTERN

async def main():
    out=Path(__file__).resolve().parents[1]/'output'/'scholarship-demo';out.mkdir(parents=True,exist_ok=True)
    base='http://127.0.0.1:8986'
    names=('BROWSER_NAVIGATION_MODE','BROWSER_ALLOWED_ORIGINS','BROWSER_PORTALS_JSON','BROWSER_ENABLE_FINAL_SUBMIT','DEMO_HOST','PUBLIC_BASE_URL')
    previous={k:os.environ.get(k) for k in names}
    os.environ.update(BROWSER_NAVIGATION_MODE='allowlist',BROWSER_ALLOWED_ORIGINS=base,BROWSER_PORTALS_JSON=json.dumps({'scholarship_practice':{'url':base+'/practice/scholarship','receipt_pattern':RECEIPT_PATTERN}}),BROWSER_ENABLE_FINAL_SUBMIT='false',DEMO_HOST='',PUBLIC_BASE_URL='')
    try:
        async with services(out,8986,8987) as (api,env):
            async with httpx.AsyncClient(base_url=api,headers={'X-Internal-Key':env['INTERNAL_KEY']},timeout=60) as client:
                async def request(method,path,body=None):
                    r=await client.request(method,path,json=body);r.raise_for_status();return r.json()
                sid=(await request('POST','/core-browser/session',{'portal_id':'scholarship_practice'}))['session_id'];root='/core-browser/session/'+sid
                try:
                    for label,value in [('Applicant name','Demo Student'),('Email address','demo@example.invalid'),('Age','20'),('Annual household income','50000'),('Course','degree')]:
                        s=await request('GET',root+'/snapshot');node=next(n for n in s['nodes'] if n['name']==label)
                        await request('POST',root+'/action',{'action_id':str(uuid.uuid4()),'type':'type','target':{'role':node['role'],'name':node['name']},'value':value,'verified':True,'source_ref':'explicit-synthetic-practice-profile'})
                    s=await request('GET',root+'/snapshot');check=next(n for n in s['nodes'] if n['role']=='checkbox')
                    await request('POST',root+'/action',{'action_id':str(uuid.uuid4()),'type':'check','target':{'role':check['role'],'name':check['name']},'checked':True,'verified':True,'source_ref':'test-explicit-synthetic-data-confirmation'})
                    s=await request('GET',root+'/snapshot');target=next(n for n in s['nodes'] if n['name']=='Submit Application')
                    task=await request('POST',root+'/human-task',{'reason':'submit','review_observation_id':s['observation_id'],'approval_ref':'practice-user-approval-'+str(uuid.uuid4()),'target_ref':target['ref'],'ttl_seconds':600})
                    async with async_playwright() as pw:
                        browser=await pw.chromium.launch(**({'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}));page=await browser.new_page(viewport={'width':390,'height':844})
                        await page.goto(task['assistance_url']);await page.get_by_role('button',name='Click Submit Application').wait_for()
                        await expect(page.locator('#expiry')).to_contain_text('expires')
                        await page.screenshot(path=str(out/'review-mobile.png'))
                        await page.get_by_role('button',name='Click Submit Application').click()
                        await page.get_by_text('Submission confirmed',exact=True).wait_for(timeout=45000)
                        assert 'Receipt: DEMO-SCH-' in await page.locator('#message').inner_text()
                        assert not await page.locator('#expiry').is_visible() and await page.locator('#expiry').inner_text()==''
                        assert not await page.locator('#screen-wrap').is_visible()
                        await page.screenshot(path=str(out/'receipt-mobile.png'));await browser.close()
                    result=await request('GET',root+'/human-task')
                    assert result['state']=='completed' and result['confirmed_by_portal'] and result['receipt_number'].startswith('DEMO-SCH-')
                    report={'mock_scholarship_form':True,'synthetic_fields_and_checkbox':True,'human_submit_confirmed':True,'confirmation_evidence':result.get('confirmation_evidence'),'receipt_number':result['receipt_number'],'timer_hidden_and_cleared':True,'automated_final_submit_enabled':False,'azure_deployed':False}
                    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
                finally:await client.delete(root)
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

if __name__=='__main__':asyncio.run(main())
