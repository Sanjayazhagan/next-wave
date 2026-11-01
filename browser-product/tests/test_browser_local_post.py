"""Regression checks for reported Azure failures; local synthetic data only."""
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import pytest
from fastapi import HTTPException
from playwright.async_api import async_playwright
from browser import core_compat as core, worker as w
from browser.general import GeneralContext, origin
from browser.general_routes import contexts

HTML = """<html><body>
<form method="post" action="/upload" enctype="multipart/form-data">
<label>Document<input type="file" name="document"></label>
<button type="submit">submit</button></form>
<form method="post" action="/application/submit"><button>Submit application</button></form>
<label>OTP Code<input type="number" autocomplete="one-time-code" id="otp"></label>
<button type="button">Verify OTP</button>
<img id="captcha_image" width="120" height="60" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='60'%3E%3Crect width='120' height='60' fill='green'/%3E%3C/svg%3E" onclick="this.dataset.clicked='yes'">
<label>CAPTCHA answer<input id="answer"></label>
<img id="ordinary" width="20" height="20" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E">
</body></html>"""

@pytest.mark.asyncio
async def test_real_upload_post_numeric_otp_and_captcha(monkeypatch):
    posted=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            raw=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            posted.append((self.path,self.rfile.read(int(self.headers.get('Content-Length',0)))))
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<p>Document upload received</p>')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('BROWSER_INTERMEDIATE_POST_ORIGINS',base)
    monkeypatch.setenv('BROWSER_ENABLE_FINAL_SUBMIT','false')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=os.environ['CHROMIUM_PATH'])
        context=await browser.new_context();page=await context.new_page()
        ctx=GeneralContext(context=context,page=page,allowed={origin(base)})
        await context.route('**/*',ctx.route);await page.goto(base)
        contexts[ctx.id]=ctx;sid=secrets.token_urlsafe(20)
        core.bridges[sid]=core.BridgeSession(ctx.id,'local')
        async def snap():return await core.snapshot(sid,w.INTERNAL_KEY)
        async def click(node):return await core.action(sid,core.CoreAction(type='click',target=core.Target(role=node['role'],name=node['name'])),w.INTERNAL_KEY)
        try:
            snapshot=await snap()
            otp=next(n for n in snapshot['nodes'] if n['name']=='OTP Code')
            assert otp['role']=='spinbutton' and otp['action_category']=='human_input'
            assert snapshot['challenge']['input']['role']=='spinbutton'
            upload=next(n for n in snapshot['nodes'] if n['name']=='submit')
            assert upload['action_category']=='upload_step'
            with pytest.raises(HTTPException) as missing:await click(upload)
            assert missing.value.status_code==409 and not posted
            snapshot=await snap();final=next(n for n in snapshot['nodes'] if n['name']=='Submit application')
            with pytest.raises(HTTPException) as blocked:await click(final)
            assert blocked.value.status_code==403 and not posted
            # Human preview identifies data-URL CAPTCHA by DOM identity and
            # permits a click only within that surface.
            task='regression-task-123'
            await core.human_begin(sid,core.HumanBegin(task_id=task,expires_at=time.time()+120),w.INTERNAL_KEY)
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            bounds=await page.locator('#captcha_image').bounding_box()
            assert bounds in view['challenge_boxes']
            await page.locator('body').evaluate("e=>e.insertAdjacentHTML('afterbegin','<p>Page changed</p>')")
            with pytest.raises(HTTPException) as stale:
                await core.human_act(sid,core.HumanAction(task_id=task,observation_id=view['observation_id'],kind='challenge_click',x=bounds['x']+10,y=bounds['y']+10),w.INTERNAL_KEY)
            assert stale.value.status_code==409
            view=await core.human_view(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            bounds=await page.locator('#captcha_image').bounding_box()
            await core.human_act(sid,core.HumanAction(task_id=task,kind='challenge_click',x=bounds['x']+10,y=bounds['y']+10),w.INTERNAL_KEY)
            assert await page.locator('#captcha_image').get_attribute('data-clicked')=='yes'
            with pytest.raises(HTTPException):
                await core.human_act(sid,core.HumanAction(task_id=task,kind='challenge_click',x=1100,y=700),w.INTERNAL_KEY)
            await core.human_finish(sid,core.HumanBegin(task_id=task),w.INTERNAL_KEY)
            snapshot=await snap();file=next(n for n in snapshot['nodes'] if n['role']=='fileupload')
            await core.action(sid,core.CoreAction(type='upload',target=core.Target(role=file['role'],name=file['name']),file_name='fixture.pdf',file_mime='application/pdf',file_base64=base64.b64encode(b'%PDF-1.4 synthetic').decode()),w.INTERNAL_KEY)
            snapshot=await snap();upload=next(n for n in snapshot['nodes'] if n['name']=='submit')
            assert (await click(upload))['ok']
            assert len(posted)==1 and posted[0][0]=='/upload' and b'%PDF-1.4 synthetic' in posted[0][1]
            assert 'Document upload received' in await page.locator('body').inner_text()
        finally:
            await core.close(sid,w.INTERNAL_KEY);await browser.close();server.shutdown();server.server_close()
