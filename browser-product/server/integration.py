"""Versioned core boundary and scoped, demo-only human verification tasks."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
import os
from urllib.parse import urlsplit
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel, ConfigDict, Field
from server.contracts import BrowserStart, BrowserCommand, PreparedDocument
from server.storage import seal

router = APIRouter()

@router.get('/integration/v1/portals')
async def portals(x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    from browser.adapters import CATALOG
    return {'portals': CATALOG}


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: str
    ttl_seconds: int = Field(default=300, ge=30, le=600)

@router.get('/assist-config')
async def assist_config():
    destination=os.getenv('WHATSAPP_RETURN_URL','')
    if destination:
        parsed=urlsplit(destination)
        if parsed.scheme!='https' or parsed.netloc!='wa.me' or parsed.query or parsed.fragment or not parsed.path.strip('/').isdigit():
            raise HTTPException(503,'Return-to-conversation destination is not configured safely')
    return {'mode':'demo','return_url':destination or None}


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    invitation: str = Field(min_length=20, max_length=150)


class Reply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer: str = Field(min_length=1, max_length=30)

class Control(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['click', 'text', 'key']
    frame_id: str
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    text: str = Field(default='', max_length=100)
    key: str = ''


def api():
    from server import app
    return app


def initialize():
    with api().conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS human_tasks (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL, worker_id TEXT NOT NULL,
          invitation_hash TEXT NOT NULL, bearer_hash TEXT, expires REAL NOT NULL,
          state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS active_human_task ON human_tasks(session_id)
          WHERE state IN ('offered','claimed');
        CREATE TABLE IF NOT EXISTS core_requests (request_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, session_id TEXT, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS core_commands (session_id TEXT NOT NULL, action_id TEXT NOT NULL, kind TEXT NOT NULL, request_hash TEXT NOT NULL, state TEXT NOT NULL, result TEXT, PRIMARY KEY(session_id,action_id));
        CREATE TABLE IF NOT EXISTS session_owners (session_id TEXT PRIMARY KEY, subject TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provenance (session_id TEXT PRIMARY KEY, fields TEXT NOT NULL, consent_ref TEXT NOT NULL);
        ''')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require_service(key):
    if not key or not hmac.compare_digest(key, api().KEY):
        raise HTTPException(401, 'Service authentication required')


def task(task_id):
    initialize()
    with api().conn() as db:
        db.execute("UPDATE human_tasks SET state='expired' WHERE expires < ? AND state IN ('offered','claimed')", (time.time(),))
        row = db.execute('SELECT * FROM human_tasks WHERE id=?', (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Task not found')
    r = dict(row)
    if r['state'] in ('offered', 'claimed'):
        s = api().row(r['session_id'])
        if s['worker_id'] != r['worker_id'] or s['state'] != 'captcha_needed':
            with api().conn() as db:
                db.execute("UPDATE human_tasks SET state='cancelled' WHERE id=?", (task_id,))
            raise HTTPException(409, 'Browser generation or challenge changed')
    return r


def authorize(task_id, authorization):
    r = task(task_id)
    token = (authorization or '').removeprefix('Bearer ')
    if r['state'] != 'claimed' or not r['bearer_hash'] or not hmac.compare_digest(digest(token), r['bearer_hash']):
        raise HTTPException(403, 'Task access expired, revoked or invalid')
    return r


@router.post('/integration/v1/human-tasks', status_code=201)
async def create_task(req: TaskRequest, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    initialize()
    s = api().row(req.session_id)
    if s['state'] != 'captcha_needed':
        raise HTTPException(409, 'No human challenge pending')
    # Live observation, not only the coordinator's stored state.
    snap = await api().worker('GET', f'/sessions/{s["worker_id"]}/challenge')
    if snap['stage'] != 'challenge':
        raise HTTPException(409, 'Portal is not showing a supported challenge')
    invitation = secrets.token_urlsafe(32)
    task_id = str(uuid.uuid4())
    expiry = time.time() + req.ttl_seconds
    with api().conn() as db:
        busy = db.execute("SELECT id FROM human_tasks WHERE session_id=? AND state='answering'", (req.session_id,)).fetchone()
        if busy:
            raise HTTPException(409, 'Human action in progress; reconcile before replacing this task')
        db.execute("UPDATE human_tasks SET state='cancelled' WHERE session_id=? AND state IN ('offered','claimed')", (req.session_id,))
        db.execute('INSERT INTO human_tasks VALUES(?,?,?,?,?,?,?,0)',
                   (task_id, req.session_id, s['worker_id'], digest(invitation), None, expiry, 'offered'))
    api().audit(req.session_id, 'human_task_offered', 'Scoped human verification task created', {'task_id': task_id})
    return {'version': '1', 'task_id': task_id, 'kind': 'captcha', 'mode': 'demo',
            'expires_at': expiry, 'assistance_path': f'/assist/{task_id}#{invitation}',
            'instructions': 'Open the link to complete the synthetic human challenge. No WhatsApp message was sent.'}


@router.get('/assist/{task_id}')
async def assistance_page(task_id: str):
    # A preview GET does not consume an invitation and exposes no task information.
    return FileResponse(api().ROOT/'web'/'assist.html', headers={
        'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})


@router.post('/assist-api/{task_id}/claim')
async def claim_task(task_id: str, req: Claim):
    r = task(task_id)
    if r['state'] != 'offered' or not hmac.compare_digest(digest(req.invitation), r['invitation_hash']):
        raise HTTPException(403, 'Invitation invalid or already claimed')
    bearer = secrets.token_urlsafe(32)
    with api().conn() as db:
        changed = db.execute("UPDATE human_tasks SET bearer_hash=?, state='claimed' WHERE id=? AND state='offered'", (digest(bearer), task_id)).rowcount
    if changed != 1:
        raise HTTPException(409, 'Task already claimed')
    return {'bearer': bearer, 'expires_at': r['expires'], 'mode': 'demo'}


@router.get('/assist-api/{task_id}/view')
async def view_task(task_id: str, authorization: str | None = Header(None)):
    r = authorize(task_id, authorization)
    return await api().worker('GET', f'/sessions/{r["worker_id"]}/challenge')


@router.post('/assist-api/{task_id}/answer')
async def answer_task(task_id: str, req: Reply, authorization: str | None = Header(None)):
    r = authorize(task_id, authorization)
    with api().conn() as db:
        changed = db.execute("UPDATE human_tasks SET state='answering', attempts=attempts+1 WHERE id=? AND state='claimed'", (task_id,)).rowcount
    if changed != 1:
        raise HTTPException(409, 'Another response is in progress')
    try:
        result = await api().challenge(r['session_id'], api().Human(challenge_answer=req.answer))
    except Exception:
        # Unknown outcome must be reconciled by core, never blindly replayed.
        with api().conn() as db:
            db.execute("UPDATE human_tasks SET state='needs_reconciliation' WHERE id=?", (task_id,))
        raise
    state = 'completed' if result['ok'] else ('failed' if r['attempts'] >= 2 else 'claimed')
    with api().conn() as db:
        db.execute('UPDATE human_tasks SET state=? WHERE id=?', (state, task_id))
    api().audit(r['session_id'], 'human_task_'+state, 'Human verification result observed', {'task_id': task_id})
    return {'ok': result['ok'], 'task_state': state, 'session_state': result['state']}


@router.get('/integration/v1/events/{session_id}')
async def integration_events(session_id: str, after: int = 0, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    result = await api().get_audit(session_id, after)
    events = [{'version': '1', 'event_id': str(e['id']), 'sequence': e['id'],
               'session_id': session_id, 'kind': e['type'], 'timestamp': e['at'],
               'summary': e['summary'], 'data': e['data']} for e in result['events']]
    return {'events': events, 'next_cursor': events[-1]['sequence'] if events else after}

@router.post('/assist-api/{task_id}/control')
async def control_task(task_id: str, req: Control, authorization: str | None = Header(None)):
    r = authorize(task_id, authorization)
    with api().conn() as db:
        changed = db.execute("UPDATE human_tasks SET state='answering' WHERE id=? AND state='claimed'", (task_id,)).rowcount
    if changed != 1:
        raise HTTPException(409, 'Another human action is in progress')
    try:
        result = await api().worker('POST', f'/sessions/{r["worker_id"]}/human-control', req.model_dump())
    except HTTPException as exc:
        with api().conn() as db:
            db.execute('UPDATE human_tasks SET state=? WHERE id=?', ('claimed' if exc.status_code in (400,403,409) else 'needs_reconciliation', task_id))
        raise
    completed = result.get('completed', False)
    with api().conn() as db:
        db.execute('UPDATE human_tasks SET state=? WHERE id=?', ('completed' if completed else 'claimed', task_id))
    if completed:
        api().update(r['session_id'], state='form_ready', review_hash=None)
        api().audit(r['session_id'], 'human_task_completed', 'Live browser verified human interaction completion', {'task_id': task_id})
    return result

@router.post('/integration/v1/human-tasks/{task_id}/cancel')
async def cancel_task(task_id: str, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    r = task(task_id)
    with api().conn() as db:
        changed = db.execute("UPDATE human_tasks SET state='cancelled', bearer_hash=NULL WHERE id=? AND state IN ('offered','claimed')", (task_id,)).rowcount
    if not changed:
        raise HTTPException(409, 'Task cannot be cancelled in its current state')
    api().audit(r['session_id'], 'human_task_cancelled', 'Human verification task cancelled')
    return {'state': 'cancelled'}


@router.get('/integration/v1/human-tasks/{task_id}')
async def task_status(task_id: str, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    r = task(task_id)
    return {k: r[k] for k in ('id', 'session_id', 'state', 'expires', 'attempts')}

@router.post('/assist-api/{task_id}/help')
async def request_help(task_id:str,authorization:str|None=Header(None)):
    r=authorize(task_id,authorization)
    api().audit(r['session_id'],'human_help_requested','Citizen requested human assistance',{'task_id':task_id})
    return {'requested':True,'message':'Help request recorded for core. The demo does not send a WhatsApp message.'}

@router.post('/integration/v1/human-tasks/{task_id}/reconcile')
async def reconcile_task(task_id:str,x_internal_key:str|None=Header(None)):
    require_service(x_internal_key)
    r=task(task_id)
    if r['state'] not in ('answering','needs_reconciliation'):
        return {'state':r['state']}
    snapshot=await api().worker('GET',f'/sessions/{r["worker_id"]}/snapshot')
    phase=snapshot['stage']
    state='completed' if phase=='form' else ('cancelled' if phase=='challenge' else 'needs_reconciliation')
    with api().conn() as db:
        db.execute('UPDATE human_tasks SET state=?,bearer_hash=NULL WHERE id=?',(state,task_id))
    if state=='completed':
        api().update(r['session_id'],state='form_ready',review_hash=None)
    api().audit(r['session_id'],'human_task_'+state,'Human step reconciled against the live browser',{'task_id':task_id})
    return {'state':state,'fresh_invitation_required':state=='cancelled'}

@router.get('/integration/v1/metrics')
async def metrics(x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    initialize()
    from server.browser_v2 import initialize as initialize_browser
    initialize_browser()
    with api().conn() as db:
        sessions = {r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM sessions GROUP BY state')}
        tasks = {r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM human_tasks GROUP BY state')}
        contexts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM browser_contexts GROUP BY state')}
    return {'mode':'demo','sessions_by_state':sessions,'human_tasks_by_state':tasks,'general_contexts_by_state':contexts}

@router.get('/integration/v1/metrics/prometheus')
async def prometheus(x_internal_key:str|None=Header(None)):
    require_service(x_internal_key)
    from server.telemetry import render
    result=await metrics(x_internal_key)
    text=render()
    for name,values in [('gradientzero_sessions',result['sessions_by_state']),('gradientzero_human_tasks',result['human_tasks_by_state']),('gradientzero_general_contexts',result['general_contexts_by_state'])]:
        text+=f'# TYPE {name} gauge\n'
        for state,count in values.items():text+=f'{name}{{state={json.dumps(state)}}} {count}\n'
    return Response(text,media_type='text/plain; version=0.0.4')


@router.post('/integration/v1/sessions', status_code=201)
async def core_start(req: BrowserStart, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    initialize()
    if set(req.fields) != set(api().DEFAULT_PROFILE) or any(not f.verified for f in req.fields.values()):
        raise HTTPException(422, 'All required fields need explicit verification and provenance')
    fingerprint = digest(req.model_dump_json())
    with api().conn() as db:
        previous = db.execute('SELECT * FROM core_requests WHERE request_id=?', (req.request_id,)).fetchone()
        if previous:
            if previous['request_hash'] != fingerprint:
                raise HTTPException(409, 'Request ID reused with changed inputs')
            if previous['state'] != 'completed':
                raise HTTPException(409, 'Start outcome requires reconciliation')
            return api().public(api().row(previous['session_id']))
        db.execute('INSERT INTO core_requests VALUES(?,?,NULL,?)', (req.request_id, fingerprint, 'pending'))
    result = await api().start(api().Start(consent=True, portal=req.portal, profile={k:f.value for k,f in req.fields.items()}))
    with api().conn() as db:
        db.execute('INSERT INTO session_owners VALUES(?,?)', (result['id'], req.subject))
        db.execute('INSERT INTO provenance VALUES(?,?,?)', (result['id'], seal(json.dumps({k:f.model_dump() for k,f in req.fields.items()}),f"provenance:{result['id']}"), seal(req.consent_ref,f"consent:{result['id']}")))
        db.execute("UPDATE core_requests SET session_id=?, state='completed' WHERE request_id=?", (result['id'], req.request_id))
    return result


@router.get('/integration/v1/sessions/{session_id}')
async def core_session(session_id: str, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    return api().public(api().row(session_id))

@router.get('/integration/v1/sessions/{session_id}/receipt')
async def core_receipt(session_id:str,x_internal_key:str|None=Header(None)):
    require_service(x_internal_key)
    return await api().receipt_pdf(session_id)


@router.post('/integration/v1/sessions/{session_id}/commands')
async def core_command(session_id: str, req: BrowserCommand, x_internal_key: str | None = Header(None)):
    require_service(x_internal_key)
    initialize()
    from server.conversation_bridge import active
    if active(session_id):raise HTTPException(409,'Citizen conversation request is awaiting resolution')
    # Never persist OTP/challenge answers, including their low-entropy hashes.
    sensitive = req.kind in ('otp', 'human')
    fingerprint = req.kind if sensitive else digest(req.model_dump_json())
    lease = str(uuid.uuid4())
    with api().conn() as db:
        db.execute('CREATE TABLE IF NOT EXISTS execution_leases (session_id TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM conversation_interrupts WHERE context_id=? AND state IN ('pending','processing','needs_reconciliation')",(session_id,)).fetchone():raise HTTPException(409,'Citizen reply is pending')
        previous = db.execute('SELECT * FROM core_commands WHERE session_id=? AND action_id=?', (session_id, req.action_id)).fetchone()
        if previous:
            if previous['request_hash'] != fingerprint:
                raise HTTPException(409, 'Action ID reused with changed inputs')
            if previous['state'] == 'completed':
                return json.loads(previous['result'])
            raise HTTPException(409, 'Action outcome unknown; reconcile instead of replaying')
        if api().row(session_id)['state'] != req.expected_state:
            raise HTTPException(409, 'Expected browser state changed')
        active = db.execute("SELECT id FROM human_tasks WHERE session_id=? AND state IN ('offered','claimed','answering') AND expires>?", (session_id, time.time())).fetchone()
        if active:
            raise HTTPException(409, 'Human task owns this step')
        db.execute('DELETE FROM execution_leases WHERE expires<?', (time.time(),))
        if not db.execute('INSERT OR IGNORE INTO execution_leases VALUES(?,?,?)', (session_id, lease, time.time()+120)).rowcount:
            raise HTTPException(409, 'Session action already in progress')
        db.execute('INSERT INTO core_commands VALUES(?,?,?,?,?,NULL)', (session_id, req.action_id, req.kind, fingerprint, 'pending'))
    try:
        a = api()
        models = {'otp':a.Otp, 'human':a.Human, 'approve':a.Approve, 'edit':a.EditProfile, 'inject':a.Chaos, 'action':a.Action}
        handlers = {'otp':a.relay_otp, 'human':a.challenge, 'fill':a.fill_form, 'approve':a.approve, 'edit':a.edit_review, 'resume':a.resume, 'reconcile':a.reconcile, 'poll':a.poll, 'inject':a.inject, 'action':a.action}
        if req.kind in models:
            from pydantic import ValidationError
            try:
                payload = models[req.kind].model_validate(req.payload)
            except ValidationError:
                raise HTTPException(422, 'Invalid command payload')
            result = await handlers[req.kind](session_id, payload)
        elif req.kind == 'fill' and req.payload:
            try:
                if set(req.payload)=={'artifact_id'}:
                    from server.artifacts import read
                    import base64
                    raw,metadata=read(session_id,req.payload['artifact_id'])
                    document=PreparedDocument.model_validate({**json.loads(metadata),'file_base64':base64.b64encode(raw).decode()})
                else:
                    document = PreparedDocument.model_validate(req.payload)
            except Exception:
                raise HTTPException(422, 'Invalid prepared document payload')
            result = await a.fill_form(session_id, document)
        else:
            result = await handlers[req.kind](session_id)
        with a.conn() as db:
            db.execute("UPDATE core_commands SET state='completed', result=? WHERE session_id=? AND action_id=?", (json.dumps(result), session_id, req.action_id))
        return result
    finally:
        with api().conn() as db:
            db.execute('DELETE FROM execution_leases WHERE token=?', (lease,))
