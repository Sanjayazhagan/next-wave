"""Scoped human-only real-browser takeover, separate from the synthetic demo.

The core must explicitly issue a challenge task. Browser control remains paused
until the person completes/cancels or the short-lived capability expires.
No OTP/CAPTCHA answer is persisted or returned to the agent.
"""
import hashlib
import hmac
import os
import secrets
import time
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router=APIRouter(tags=['real human takeover'])

class Offer(BaseModel):
    reason: str = Field(pattern=r'^(otp|captcha|login|upload|verification|other)$')
    ttl_seconds: int = Field(default=300,ge=60,le=600)

class Control(BaseModel):
    observation_id: str | None = None
    kind: str = Field(pattern=r'^(fill|click|challenge_click)$')
    target_ref: str | None=None
    value: str = Field(default='',max_length=100)
    x: float | None=None
    y: float | None=None


def api():
    from server import app
    return app


def database():
    from server import app
    with app.conn() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS core_assist_tasks (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL, token_hash TEXT NOT NULL,
          expires REAL NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL,
          created REAL NOT NULL);
          CREATE INDEX IF NOT EXISTS core_assist_by_session ON core_assist_tasks(session_id,state);''')


def digest(token):return hashlib.sha256(token.encode()).hexdigest()


def lookup(task_id,token):
    database()
    with api().conn() as db:
        db.execute("UPDATE core_assist_tasks SET state='expired' WHERE expires<? AND state='active'",(time.time(),))
        entry=db.execute('SELECT * FROM core_assist_tasks WHERE id=?',(task_id,)).fetchone()
    if not entry or entry['state']!='active' or entry['expires']<=time.time() or not token or not hmac.compare_digest(digest(token),entry['token_hash']):
        raise HTTPException(403,'Human assistance link expired or invalid')
    return dict(entry)


def authenticated(x_internal_key):
    from server.integration import require_service
    require_service(x_internal_key)


@router.post('/core-browser/session/{sid}/human-task',status_code=201)
async def offer(sid:str,req:Offer,request:Request,x_internal_key:str|None=Header(None)):
    authenticated(x_internal_key)
    database()
    with api().conn() as db:
        if db.execute("SELECT 1 FROM core_assist_tasks WHERE session_id=? AND state='active' AND expires>?",(sid,time.time())).fetchone():
            raise HTTPException(409,'Human assistance already pending for session')
    token=secrets.token_urlsafe(32);task_id=str(uuid.uuid4());expiry=time.time()+req.ttl_seconds
    # Worker first: invalid browser-session IDs must not mint usable public URLs.
    await api().worker('POST',f'/core/session/{sid}/human-begin',{'task_id':task_id,'expires_at':expiry})
    with api().conn() as db:
        db.execute('INSERT INTO core_assist_tasks VALUES (?,?,?,?,?,?,?)',
                   (task_id,sid,digest(token),expiry,req.reason,'active',time.time()))
    api().audit(sid,'real_human_task_offered','Scoped real browser verification requested',{'task_id':task_id,'reason':req.reason})
    path=f'/core-assist/{task_id}#{token}'
    # Explicit deployment host prevents an attacker-controlled Host header from
    # generating a phishing link; the fragment is never sent in HTTP requests.
    hostname=os.getenv('DEMO_HOST','')
    site=('https://'+hostname) if hostname and not any(ch in hostname for ch in '/?#@ ') else ''
    return {'task_id':task_id,'expires_at':expiry,'assistance_path':path,
            'assistance_url':site+path if site else None,'reason':req.reason,
            'note':'Share the link only with the citizen; no WhatsApp message is sent automatically.'}


@router.get('/core-browser/session/{sid}/human-task')
async def status(sid:str,x_internal_key:str|None=Header(None)):
    authenticated(x_internal_key);database()
    with api().conn() as db:
        db.execute("UPDATE core_assist_tasks SET state='expired' WHERE expires<? AND state='active'",(time.time(),))
        entry=db.execute('SELECT id,reason,state,expires FROM core_assist_tasks WHERE session_id=? ORDER BY created DESC LIMIT 1',(sid,)).fetchone()
    return dict(entry) if entry else {'state':'none'}


@router.get('/core-assist/{task_id}',name='core_assist_page')
async def page(task_id:str):
    from server.app import ROOT
    # No task IDs/secrets are placed in the HTML. The URL fragment is read by JS.
    return FileResponse(ROOT/'web'/'core_assist.html',headers={
        'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
        'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'"})


@router.get('/core-assist.js')
async def js():
    from server.app import ROOT
    return FileResponse(ROOT/'web'/'core_assist.js',media_type='application/javascript',headers={'Cache-Control':'no-store'})


@router.get('/core-assist.css')
async def css():
    from server.app import ROOT
    return FileResponse(ROOT/'web'/'core_assist.css',media_type='text/css',headers={'Cache-Control':'no-store'})


@router.get('/core-assist/{task_id}/view')
async def view(task_id:str,x_assist_token:str|None=Header(None)):
    entry=lookup(task_id,x_assist_token)
    result=await api().worker('POST',f'/core/session/{entry["session_id"]}/human-view',{'task_id':task_id})
    return {'reason':entry['reason'],'expires_at':entry['expires'],**result}


@router.post('/core-assist/{task_id}/control')
async def control(task_id:str,req:Control,x_assist_token:str|None=Header(None)):
    entry=lookup(task_id,x_assist_token)
    payload={**req.model_dump(),'task_id':task_id}
    return await api().worker('POST',f'/core/session/{entry["session_id"]}/human-act',payload)


@router.post('/core-assist/{task_id}/complete')
async def complete(task_id:str,x_assist_token:str|None=Header(None)):
    entry=lookup(task_id,x_assist_token)
    res=await api().worker('POST',f'/core/session/{entry["session_id"]}/human-finish',{'task_id':task_id})
    with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='completed' WHERE id=? AND state='active'",(task_id,))
    api().audit(entry['session_id'],'real_human_task_completed','Human returned browser control; core must verify outcome',{'task_id':task_id})
    return {**res,'note':'Completion was citizen-attested; core MUST re-observe the page and decide whether verification succeeded.'}


@router.post('/core-browser/session/{sid}/human-task/cancel')
async def cancel(sid:str,x_internal_key:str|None=Header(None)):
    authenticated(x_internal_key);database()
    with api().conn() as db:
        entry=db.execute("SELECT id FROM core_assist_tasks WHERE session_id=? AND state='active' AND expires>? ORDER BY created DESC LIMIT 1",(sid,time.time())).fetchone()
        if not entry:raise HTTPException(404,'No active assistance task')
    result=await api().worker('POST',f'/core/session/{sid}/human-cancel',{'task_id':entry['id']})
    with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='cancelled' WHERE id=?",(entry['id'],))
    return result
