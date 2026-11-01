"""Real HTTP + mobile UI submit-only handoff on an isolated practice fixture."""
import asyncio
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from playwright.async_api import async_playwright
from scripts.test_harness import services

async def main():
    out=Path(__file__).resolve().parents[1]/'output'/'human-submit';out.mkdir(parents=True,exist_ok=True)
    posts=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<p>Application successfully submitted. Receipt: PRACTICE-123</p>' if self.path=='/receipt' else b'<form action="/submit" method="post"><label>Name<input name="name" value="Synthetic citizen"></label><button>Submit Application</button></form><button>Help</button>')
        def do_POST(self):
            posts.append(self.rfile.read(int(self.headers.get('Content-Length','0'))));self.send_response(303);self.send_header('Location','/receipt');self.end_headers()
        def log_message(self,*args):pass
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=fixture.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{fixture.server_port}'
    names=('BROWSER_NAVIGATION_MODE','BROWSER_ALLOWED_ORIGINS','BROWSER_PORTALS_JSON','BROWSER_ENABLE_FINAL_SUBMIT','DEMO_HOST','PUBLIC_BASE_URL')
    previous={k:os.environ.get(k) for k in names}
    os.environ.update(BROWSER_NAVIGATION_MODE='allowlist',BROWSER_ALLOWED_ORIGINS=url,BROWSER_PORTALS_JSON=json.dumps({'practice':{'url':url,'receipt_pattern':r'Receipt: (PRACTICE-\d+)'}}),BROWSER_ENABLE_FINAL_SUBMIT='false',DEMO_HOST='',PUBLIC_BASE_URL='')
    try:
        async with services(out,8966,8967) as (base,env):
            async with httpx.AsyncClient(base_url=base,headers={'X-Internal-Key':env['INTERNAL_KEY']},timeout=60) as c:
                r=await c.post('/core-browser/session',json={'portal_id':'practice'});r.raise_for_status();sid=r.json()['session_id'];root='/core-browser/session/'+sid
                try:
                    s=(await c.get(root+'/snapshot')).json();target=next(n for n in s['nodes'] if n['name']=='Submit Application')
                    auto=await c.post(root+'/action',json={'type':'click','target':{'role':target['role'],'name':target['name']},'action_id':str(uuid.uuid4())})
                    assert auto.status_code==403 and not posts
                    body={'reason':'submit','review_observation_id':s['observation_id'],'approval_ref':'synthetic-citizen-approval-'+str(uuid.uuid4()),'target_ref':target['ref'],'ttl_seconds':600}
                    r=await c.post(root+'/human-task',json=body);r.raise_for_status();task=r.json()
                    assert task['assistance_url']==base+task['assistance_path'] and task['single_use']
                    token=task['assistance_path'].split('#')[1]
                    async with async_playwright() as pw:
                        b=await pw.chromium.launch(**({'executable_path':os.environ['CHROMIUM_PATH']} if os.getenv('CHROMIUM_PATH') else {}))
                        page=await b.new_page(viewport={'width':390,'height':844});await page.goto(task['assistance_url'])
                        button=page.get_by_role('button',name='Click Submit Application');await button.wait_for()
                        assert await page.locator('#controls input').count()==0 and not await page.locator('#done').is_visible()
                        await button.click();await page.get_by_text('Submission confirmed',exact=True).wait_for(timeout=45000)
                        assert 'PRACTICE-123' in await page.locator('#message').inner_text()
                        await page.screenshot(path=str(out/'completed-mobile.png'));await b.close()
                    status=(await c.get(root+'/human-task')).json()
                    assert status['state']=='completed' and status['receipt_number']=='PRACTICE-123' and status['confirmed_by_portal'] and len(posts)==1
                    replay=await c.post('/core-assist/'+task['task_id']+'/control',headers={'X-Assist-Token':token},json={'kind':'click','target_ref':target['ref'],'observation_id':s['observation_id']})
                    assert replay.status_code==403 and len(posts)==1
                    assert (await c.get(root+'/snapshot')).status_code==200
                    result={'scope':'synthetic practice portal, real HTTP and mobile browser UI','automated_final_submit_disabled':True,'submit_only_ui':True,'same_session_receipt':'PRACTICE-123','bot_poll_receipt':True,'single_use_second_click_refused':True,'native_posts':len(posts),'absolute_assistance_url':True,'real_portal_or_azure_deployment_verified':False}
                    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
                finally:await c.delete(root)
    finally:
        fixture.shutdown();fixture.server_close()
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

if __name__=='__main__':asyncio.run(main())
