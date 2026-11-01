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
    reason: str = Field(pattern=r'^(otp|captcha|login|upload|verification|submit|other)$')
    review_observation_id: str | None = Field(default=None,min_length=8,max_length=100)
    approval_ref: str | None = Field(default=None,min_length=8,max_length=200)
    target_ref: str | None = Field(default=None,max_length=100)
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
          CREATE INDEX IF NOT EXISTS core_assist_by_session ON core_assist_tasks(session_id,state);
          CREATE TABLE IF NOT EXISTS core_assist_results (task_id TEXT PRIMARY KEY,payload TEXT NOT NULL);''')


def digest(token):return hashlib.sha256(token.encode()).hexdigest()


def lookup(task_id,token):
    database()
    with api().conn() as db:
        db.execute("UPDATE core_assist_tasks SET state='expired' WHERE expires<? AND state IN ('offering','active','completing','needs_reconciliation') AND (reason!='submit' OR state IN ('offering','active'))",(time.time(),))
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
    from server.submit_tasks import public_origin
    site=public_origin(request)
    if req.reason=='submit' and (not req.review_observation_id or not req.approval_ref):raise HTTPException(422,'submit requires review_observation_id and approval_ref')
    with api().conn() as db:
        if db.execute("SELECT 1 FROM core_assist_tasks WHERE session_id=? AND ((state IN ('offering','active','completing','needs_reconciliation') AND expires>?) OR (reason='submit' AND state IN ('submitting','uncertain','completed','needs_reconciliation')))",(sid,time.time())).fetchone():
            raise HTTPException(409,'Human assistance already pending for session')
    token=secrets.token_urlsafe(32);task_id=str(uuid.uuid4());expiry=time.time()+(600 if req.reason=='submit' and 'ttl_seconds' not in req.model_fields_set else req.ttl_seconds)
    with api().conn() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM core_assist_tasks WHERE session_id=? AND ((state IN ('offering','active','completing','needs_reconciliation') AND expires>?) OR (reason='submit' AND state IN ('submitting','uncertain','completed','needs_reconciliation')))",(sid,time.time())).fetchone():
            raise HTTPException(409,'Human assistance already pending for session')
        db.execute('INSERT INTO core_assist_tasks VALUES (?,?,?,?,?,?,?)',
                   (task_id,sid,digest(token),expiry,req.reason,'offering',time.time()))
    try:
        await api().worker('POST',f'/core/session/{sid}/human-begin',{'task_id':task_id,'expires_at':expiry,'reason':req.reason,**({'review_observation_id':req.review_observation_id,'approval_ref':req.approval_ref,'target_ref':req.target_ref} if req.reason=='submit' else {})})
        with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='active' WHERE id=?",(task_id,))
    except BaseException as exc:
        known=isinstance(exc,HTTPException) and (exc.status_code in (400,401,403,404,409,410,422) or (exc.headers or {}).get('X-Browser-Outcome')=='not_applied')
        with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state=? WHERE id=?",('rejected' if known else 'needs_reconciliation',task_id))
        raise
    api().audit(sid,'real_human_task_offered','Scoped real browser verification requested',{'task_id':task_id,'reason':req.reason})
    path=f'/core-assist/{task_id}#{token}'
    # Explicit deployment host prevents an attacker-controlled Host header from
    # generating a phishing link; the fragment is never sent in HTTP requests.
    return {'task_id':task_id,'expires_at':expiry,'assistance_path':path,
            'assistance_url':site+path if site else None,'reason':req.reason,'single_use':req.reason=='submit',
            'note':'Share the link only with the citizen; no WhatsApp message is sent automatically.'}


@router.get('/core-browser/session/{sid}/human-task')
async def status(sid:str,x_internal_key:str|None=Header(None)):
    authenticated(x_internal_key);database()
    with api().conn() as db:
        db.execute("UPDATE core_assist_tasks SET state='expired' WHERE expires<? AND state IN ('offering','active','completing','needs_reconciliation') AND (reason!='submit' OR state IN ('offering','active'))",(time.time(),))
        entry=db.execute('SELECT id,session_id,reason,state,expires FROM core_assist_tasks WHERE session_id=? ORDER BY created DESC LIMIT 1',(sid,)).fetchone()
    if not entry:return {'state':'none'}
    if entry['reason']=='submit':
        from server.submit_tasks import status as submit_status
        return await submit_status(dict(entry))
    result=dict(entry)
    if result['state'] in ('offering','active','completing','needs_reconciliation'):
        try:
            live=await api().worker('GET',f'/core/session/{sid}/human-status')
            if live.get('task_id')!=result['id']:
                result['state']='needs_reconciliation'
                with api().conn() as db:
                    db.execute("UPDATE core_assist_tasks SET state='needs_reconciliation' WHERE id=? AND state=?",(result['id'],entry['state']))
                    current=db.execute('SELECT state FROM core_assist_tasks WHERE id=?',(result['id'],)).fetchone()
                    if current:result['state']=current['state']
        except HTTPException as exc:
            result['state']='needs_reconciliation'
            result['worker_available']=False
    return result


@router.get('/core-assist/{task_id}',name='core_assist_page')
async def page(task_id:str):
    from server.app import ROOT
    # No task IDs/secrets are placed in the HTML. The URL fragment is read by JS.
    return FileResponse(ROOT/'web'/'core_assist.html',headers={
        'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
          'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})


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
    try:result=await api().worker('POST',f'/core/session/{entry["session_id"]}/human-view',{'task_id':task_id},timeout=45)
    except HTTPException as exc:
        if entry['reason']=='submit' and exc.status_code==409:
            from server.submit_tasks import persist
            persist(task_id,{'state':'review_changed','confirmed_by_portal':False,'receipt_number':None,'needs_new_review':True,'click_attempted':False,'needs_reconciliation':False})
        raise
    return {'reason':entry['reason'],'expires_at':entry['expires'],**result}


@router.post('/core-assist/{task_id}/control')
async def control(task_id:str,req:Control,x_assist_token:str|None=Header(None)):
    entry=lookup(task_id,x_assist_token)
    if entry['reason']=='submit':
        from server.submit_tasks import control as submit_control
        return await submit_control(entry,req)
    payload={**req.model_dump(),'task_id':task_id}
    return await api().worker('POST',f'/core/session/{entry["session_id"]}/human-act',payload)


@router.post('/core-assist/{task_id}/complete')
async def complete(task_id:str,x_assist_token:str|None=Header(None)):
    entry=lookup(task_id,x_assist_token)
    if entry['reason']=='submit':raise HTTPException(403,'Use the one reviewed Submit control; submit tasks cannot be completed by attestation')
    with api().conn() as db:
        changed=db.execute("UPDATE core_assist_tasks SET state='completing' WHERE id=? AND state='active'",(task_id,)).rowcount
        if not changed:raise HTTPException(409,'Assistance completion already processing')
    try:
        res=await api().worker('POST',f'/core/session/{entry["session_id"]}/human-finish',{'task_id':task_id})
        with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='completed' WHERE id=?",(task_id,))
    except BaseException:
        with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='needs_reconciliation' WHERE id=?",(task_id,))
        raise
    api().audit(entry['session_id'],'real_human_task_completed','Human returned browser control; core must verify outcome',{'task_id':task_id})
    return {**res,'note':'Completion was citizen-attested; core MUST re-observe the page and decide whether verification succeeded.'}


@router.post('/core-browser/session/{sid}/human-task/cancel')
async def cancel(sid:str,x_internal_key:str|None=Header(None)):
    authenticated(x_internal_key);database()
    with api().conn() as db:
        entry=db.execute("SELECT id FROM core_assist_tasks WHERE session_id=? AND ((state IN ('offering','active','completing','needs_reconciliation') AND expires>?) OR (reason='submit' AND state IN ('submitting','uncertain','completed','needs_reconciliation'))) ORDER BY created DESC LIMIT 1",(sid,time.time())).fetchone()
        if not entry:raise HTTPException(404,'No active assistance task')
    result=await api().worker('POST',f'/core/session/{sid}/human-cancel',{'task_id':entry['id']})
    with api().conn() as db:db.execute("UPDATE core_assist_tasks SET state='cancelled' WHERE id=?",(entry['id'],))
    return result
