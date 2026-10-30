"""Browser ↔ core conversation transport. Does not send messages or run an agent."""
import hashlib
import hmac
import json
import re
import math
import secrets
import time
import uuid
from typing import Literal
from fastapi import APIRouter,Header,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from server.storage import seal,unseal,cipher

router=APIRouter(prefix='/integration/v2/conversation')
SECRET=re.compile(r'password|\botp\b|one.?time|captcha|security.?code',re.I)


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Question(Strict):
    name:str=Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,49}$')
    label:str=Field(min_length=1,max_length=200)
    kind:Literal['text','number','date','choice','artifact']='text'
    required:bool=True
    choices:list[str]=Field(default_factory=list,max_length=30)

class Interrupt(Strict):
    request_id:str=Field(min_length=8,max_length=100)
    context_id:str
    generation:str
    subject:str=Field(min_length=1,max_length=100)
    kind:Literal['information','otp','captcha','device_auth','approval','helper']
    prompt:str=Field(min_length=1,max_length=1500)
    fields:list[Question]=Field(default_factory=list,max_length=30)
    review_hash:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    ttl_seconds:int=Field(default=600,ge=30,le=1800)

class CitizenReply(Strict):
    response_id:str=Field(min_length=8,max_length=100)
    subject:str
    generation:str
    values:dict[str,str]=Field(default_factory=dict)
    secret:str|None=Field(default=None,min_length=1,max_length=32)
    decision:Literal['approve','edit','reject']|None=None
    review_hash:str|None=None

class DeliveryClaim(Strict):
    consumer_id:str=Field(min_length=1,max_length=100)

class DeliveryAck(DeliveryClaim):
    lease_token:str=Field(min_length=20,max_length=100)
    provider_message_id:str=Field(min_length=1,max_length=200)

class Notification(Strict):
    notification_id:str=Field(min_length=8,max_length=100)
    context_id:str
    generation:str
    subject:str
    kind:Literal['progress','result','status','error']
    summary:str=Field(min_length=1,max_length=1500)
    receipt_ref:str|None=None
    artifact_ids:list[str]=Field(default_factory=list,max_length=10)


def api():
    from server import app
    return app


def initialize():
    with api().conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS conversation_interrupts(id TEXT PRIMARY KEY,request_id TEXT UNIQUE,fingerprint TEXT NOT NULL,context_id TEXT NOT NULL,generation TEXT NOT NULL,subject TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,request TEXT NOT NULL,response_id TEXT,response TEXT,child_task TEXT,attempts INTEGER DEFAULT 0,created REAL NOT NULL,expires REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS conversation_active ON conversation_interrupts(context_id) WHERE state IN ('pending','processing');
        CREATE TABLE IF NOT EXISTS conversation_deliveries(id TEXT PRIMARY KEY,interrupt_id TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,consumer TEXT,lease_hash TEXT,lease_until REAL,provider_ref TEXT,attempts INTEGER DEFAULT 0,created REAL NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS conversation_responses(interrupt_id TEXT,response_id TEXT,fingerprint TEXT,state TEXT NOT NULL,result TEXT,PRIMARY KEY(interrupt_id,response_id));
        ''')


def require(key):
    from server.integration import require_service
    require_service(key)
    try:cipher()
    except (RuntimeError,ValueError):raise HTTPException(503,'Configure encryption before creating conversation requests')
    initialize()


def execution(ident):
    from server.browser_v2 import initialize as init_browser
    init_browser()
    with api().conn() as db:
        r=db.execute('SELECT * FROM browser_contexts WHERE id=?',(ident,)).fetchone()
        owner=db.execute('SELECT subject FROM session_owners WHERE session_id=?',(ident,)).fetchone()
    if r:
        if r['state']!='active':raise HTTPException(409,'Browser execution is not active')
        return {'generation':r['generation'],'subject':r['subject'],'type':'general','row':dict(r)}
    r=api().row(ident)
    if not owner:raise HTTPException(409,'Core must establish session ownership before conversation delivery')
    return {'generation':r['worker_id'],'subject':owner['subject'],'type':'adapter','row':r}


def expire():
    initialize()
    with api().conn() as db:
        db.execute("UPDATE conversation_interrupts SET state='expired' WHERE expires<? AND state IN ('pending','notification_ready')",(time.time(),))
        db.execute("UPDATE conversation_interrupts SET state='needs_reconciliation' WHERE expires<? AND state='processing'",(time.time(),))
        db.execute("UPDATE conversation_deliveries SET state='expired' WHERE expires<? AND state IN ('queued','leased')",(time.time(),))
        db.execute("UPDATE conversation_interrupts SET state='completed' WHERE state='pending' AND child_task IN (SELECT id FROM human_tasks WHERE state='completed')")
        for child_state in ('failed','expired','needs_reconciliation'):
            db.execute('UPDATE conversation_interrupts SET state=? WHERE state=\'pending\' AND child_task IN (SELECT id FROM human_tasks WHERE state=?)',(child_state,child_state))


def active(ident):
    expire()
    with api().conn() as db:return bool(db.execute("SELECT 1 FROM conversation_interrupts WHERE context_id=? AND state IN ('pending','processing','needs_reconciliation')",(ident,)).fetchone())


def get(ident):
    expire()
    with api().conn() as db:r=db.execute('SELECT * FROM conversation_interrupts WHERE id=?',(ident,)).fetchone()
    if not r:raise HTTPException(404,'Conversation request not found')
    result=dict(r)
    if result['child_task'] and result['state']=='pending':
        with api().conn() as db:child=db.execute('SELECT state FROM human_tasks WHERE id=?',(result['child_task'],)).fetchone()
        if child and child['state']=='completed':
            with api().conn() as db:db.execute("UPDATE conversation_interrupts SET state='completed' WHERE id=? AND state='pending'",(ident,))
            result['state']='completed'
    return result


@router.post('/interrupts',status_code=201)
async def create(req:Interrupt,x_internal_key:str|None=Header(None)):
    require(x_internal_key);expire()
    fingerprint=hashlib.sha256(req.model_dump_json().encode()).hexdigest()
    with api().conn() as db:previous=db.execute('SELECT id,fingerprint,state FROM conversation_interrupts WHERE request_id=?',(req.request_id,)).fetchone()
    if previous:
        if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Request ID changed')
        return {'interrupt_id':previous['id'],'state':previous['state'],'replayed':True}
    current=execution(req.context_id)
    if (req.subject,req.generation)!=(current['subject'],current['generation']):raise HTTPException(409,'Recipient or browser generation mismatch')
    if req.kind=='device_auth':raise HTTPException(501,'Official device-auth completion needs a reviewed portal/device adapter')
    if req.kind=='otp' and current['type']=='adapter' and current['row']['state']!='otp_needed':raise HTTPException(409,'Browser is not waiting for OTP')
    if req.kind=='information' and (not req.fields or any(SECRET.search(q.name+' '+q.label) for q in req.fields)):raise HTTPException(422,'Information requests require non-secret named fields')
    if len({q.name for q in req.fields})!=len(req.fields):raise HTTPException(422,'Question names must be unique')
    if any(q.kind=='choice' and not q.choices for q in req.fields):raise HTTPException(422,'Choice questions require offered values')
    if req.kind=='approval':
        if not req.review_hash:raise HTTPException(422,'Approval must be bound to a review hash')
        if current['type']=='adapter' and current['row']['review_hash']!=req.review_hash:raise HTTPException(409,'Review changed')
    if req.kind in ('otp','captcha','device_auth') and current['type']=='general':
        raise HTTPException(501,'This context needs a reviewed authentication/human adapter before secret or device interaction can be routed')
    ident=str(uuid.uuid4());now=time.time()
    with api().conn() as db:
        db.execute('BEGIN IMMEDIATE')
        previous=db.execute('SELECT id,fingerprint FROM conversation_interrupts WHERE request_id=?',(req.request_id,)).fetchone()
        if previous:
            if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Request ID changed')
            return {'interrupt_id':previous['id'],'replayed':True}
        if db.execute("SELECT 1 FROM conversation_interrupts WHERE context_id=? AND state IN ('pending','processing','needs_reconciliation')",(req.context_id,)).fetchone():raise HTTPException(409,'Resolve the current conversation request first')
        db.execute('CREATE TABLE IF NOT EXISTS execution_leases(session_id TEXT PRIMARY KEY,token TEXT NOT NULL,expires REAL NOT NULL)')
        if db.execute('SELECT 1 FROM execution_leases WHERE session_id=? AND expires>?',(req.context_id,now)).fetchone():raise HTTPException(409,'Wait for the current browser action before pausing for a citizen reply')
        db.execute('INSERT INTO conversation_interrupts(id,request_id,fingerprint,context_id,generation,subject,kind,state,request,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,req.request_id,fingerprint,req.context_id,req.generation,req.subject,req.kind,'pending',seal(req.model_dump_json(),f'interrupt:{ident}'),now,now+req.ttl_seconds))
    assistance=None
    if req.kind=='captcha':
        from server.integration import create_task,TaskRequest
        try:child=await create_task(TaskRequest(session_id=req.context_id,ttl_seconds=min(600,req.ttl_seconds)),api().KEY)
        except Exception:
            with api().conn() as db:db.execute("UPDATE conversation_interrupts SET state='failed' WHERE id=?",(ident,))
            raise
        assistance=child['assistance_path']
        with api().conn() as db:db.execute('UPDATE conversation_interrupts SET child_task=? WHERE id=?',(child['task_id'],ident))
    delivery=str(uuid.uuid4())
    message={'version':'2','delivery_id':delivery,'interrupt_id':ident,'context_id':req.context_id,'generation':req.generation,'subject':req.subject,'kind':req.kind,'prompt':req.prompt,'fields':[q.model_dump() for q in req.fields],'review_hash':req.review_hash,'assistance_path':assistance,'expires_at':now+req.ttl_seconds,'transport':'core_owned_whatsapp_or_other','synthetic_runtime':True}
    with api().conn() as db:db.execute('INSERT INTO conversation_deliveries(id,interrupt_id,state,payload,created,expires) VALUES(?,?,?,?,?,?)',(delivery,ident,'queued',seal(json.dumps(message),f'delivery:{delivery}'),now,now+req.ttl_seconds))
    api().audit(req.context_id,'conversation_request_ready','Citizen conversation request queued for core',{'interrupt_id':ident,'kind':req.kind})
    return {'interrupt_id':ident,'delivery_id':delivery,'state':'pending','replayed':False}


@router.get('/interrupts/{ident}')
async def status(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=get(ident)
    return {k:r[k] for k in ('id','context_id','generation','kind','state','attempts','expires','response_id')}


@router.post('/deliveries/claim')
async def claim(req:DeliveryClaim,x_internal_key:str|None=Header(None)):
    require(x_internal_key);expire();now=time.time();token=secrets.token_urlsafe(32)
    with api().conn() as db:
        db.execute('BEGIN IMMEDIATE')
        r=db.execute("SELECT d.* FROM conversation_deliveries d JOIN conversation_interrupts i ON i.id=d.interrupt_id WHERE (d.state='queued' OR (d.state='leased' AND d.lease_until<?)) AND d.expires>? AND i.state IN ('pending','notification_ready') ORDER BY d.created LIMIT 1",(now,now)).fetchone()
        if not r:return {'delivery':None}
        db.execute("UPDATE conversation_deliveries SET state='leased',consumer=?,lease_hash=?,lease_until=?,attempts=attempts+1 WHERE id=?",(req.consumer_id,hashlib.sha256(token.encode()).hexdigest(),now+60,r['id']))
    return {'delivery':json.loads(unseal(r['payload'],f'delivery:{r["id"]}')),'lease_token':token,'lease_until':now+60,'delivery_semantics':'at_least_once; consumer must deduplicate delivery_id'}


@router.post('/deliveries/{ident}/ack')
async def ack(ident:str,req:DeliveryAck,x_internal_key:str|None=Header(None)):
    require(x_internal_key);expire()
    with api().conn() as db:
        r=db.execute('SELECT * FROM conversation_deliveries WHERE id=?',(ident,)).fetchone()
        if not r or r['consumer']!=req.consumer_id or not r['lease_hash'] or not hmac.compare_digest(r['lease_hash'],hashlib.sha256(req.lease_token.encode()).hexdigest()):raise HTTPException(403,'Delivery lease mismatch')
        if r['state']=='sent':return {'state':'sent','replayed':True}
        if r['state']!='leased' or r['lease_until']<time.time():raise HTTPException(409,'Delivery lease expired')
        db.execute("UPDATE conversation_deliveries SET state='sent',provider_ref=? WHERE id=?",(seal(req.provider_message_id,f'delivery-ref:{ident}'),ident))
        db.execute("UPDATE conversation_interrupts SET state='completed' WHERE id=? AND state='notification_ready'",(r['interrupt_id'],))
    return {'state':'sent','replayed':False}


@router.post('/interrupts/{ident}/responses')
async def respond(ident:str,req:CitizenReply,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=get(ident)
    if req.subject!=r['subject']:raise HTTPException(403,'Reply recipient mismatch')
    if req.generation!=r['generation']:raise HTTPException(409,'Reply belongs to an old generation')
    material=req.model_dump(exclude={'secret'})
    fingerprint=hmac.new(api().SIGN_KEY.encode(),json.dumps(material,sort_keys=True).encode(),hashlib.sha256).hexdigest()
    with api().conn() as db:previous=db.execute('SELECT * FROM conversation_responses WHERE interrupt_id=? AND response_id=?',(ident,req.response_id)).fetchone()
    if previous:
        if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Response ID reused with changed metadata')
        if previous['state']!='completed':raise HTTPException(409,'Response outcome requires reconciliation; do not replay secret')
        return {**json.loads(unseal(previous['result'],f'conversation-attempt:{ident}:{req.response_id}')),'replayed':True}
    current=execution(r['context_id'])
    if current['generation']!=r['generation']:raise HTTPException(409,'Browser generation changed')
    if r['state']=='completed' and r['response_id']==req.response_id:return {'state':'completed','replayed':True}
    if r['state']!='pending':raise HTTPException(409,'Request is not awaiting a reply')
    original=Interrupt.model_validate_json(unseal(r['request'],f'interrupt:{ident}'))
    if r['kind'] in ('otp','captcha'):
        if not req.secret or req.values or req.decision:raise HTTPException(422,'A transient verification response is required')
    else:
        if req.secret:raise HTTPException(422,'Secrets must not be submitted as conversation information')
        if len(req.values)>30 or any(SECRET.search(k) or len(v)>2000 for k,v in req.values.items()):raise HTTPException(422,'Use bounded non-secret reply fields')
        if r['kind']=='information':
            fields={q.name:q for q in original.fields}
            if set(req.values)-set(fields) or any(q.required and not req.values.get(q.name) for q in fields.values()):raise HTTPException(422,'Reply fields do not match the request')
            for name,value in req.values.items():
                q=fields[name]
                if len(value)>2000:raise HTTPException(422,'Reply value too long')
                if q.kind=='choice' and value not in q.choices:raise HTTPException(422,'Choose an offered value')
                if q.kind=='number':
                    try:
                        if not math.isfinite(float(value)):raise ValueError()
                    except ValueError:raise HTTPException(422,'Numeric reply required')
                if q.kind=='date':
                    from datetime import date
                    try:date.fromisoformat(value)
                    except ValueError:raise HTTPException(422,'Use an ISO date')
                if q.kind=='artifact':
                    from server.artifacts import read
                    read(r['context_id'],value)
        if r['kind']=='approval' and (not req.decision or req.review_hash!=original.review_hash):raise HTTPException(409,'Approval/edit must match this exact declared review hash')
        if r['kind']=='approval' and current['type']=='adapter' and (current['row']['state']!='approval_needed' or current['row']['review_hash']!=original.review_hash):raise HTTPException(409,'Current browser review no longer matches this approval request')
    with api().conn() as db:
        changed=db.execute("UPDATE conversation_interrupts SET state='processing',attempts=attempts+1 WHERE id=? AND state='pending'",(ident,)).rowcount
        if changed:db.execute('INSERT INTO conversation_responses VALUES(?,?,?,?,NULL)',(ident,req.response_id,fingerprint,'pending'))
    if not changed:raise HTTPException(409,'Another reply is being processed')
    try:
        if r['kind']=='otp':result=await api().relay_otp(r['context_id'],api().Otp(otp=req.secret))
        elif r['kind']=='captcha':
            if r['child_task']:
                with api().conn() as db:child=db.execute('SELECT state FROM human_tasks WHERE id=?',(r['child_task'],)).fetchone()
                if child and child['state'] not in ('offered','cancelled'):raise HTTPException(409,'Interactive human task already claimed; finish it there')
                with api().conn() as db:db.execute("UPDATE human_tasks SET state='cancelled',bearer_hash=NULL WHERE id=?",(r['child_task'],))
            result=await api().challenge(r['context_id'],api().Human(challenge_answer=req.secret))
        else:result={'ok':True}
    except Exception:
        with api().conn() as db:db.execute("UPDATE conversation_interrupts SET state='needs_reconciliation' WHERE id=?",(ident,))
        raise
    completed=result.get('ok',False);next_state='completed' if completed else ('failed' if r['attempts']>=2 else 'pending')
    stored=None if r['kind'] in ('otp','captcha') else seal(json.dumps({'values':req.values,'decision':req.decision,'review_hash':req.review_hash,'verification_status':'citizen_provided_not_document_verified'}),f'interrupt-response:{ident}')
    final={'interrupt_id':ident,'context_id':r['context_id'],'generation':r['generation'],'state':next_state,'replayed':False,'secret_persisted':False,'browser_result':result,'submission_performed':False}
    with api().conn() as db:
        db.execute('UPDATE conversation_interrupts SET state=?,response_id=?,response=? WHERE id=?',(next_state,req.response_id,stored,ident))
        db.execute("UPDATE conversation_responses SET state='completed',result=? WHERE interrupt_id=? AND response_id=?",(seal(json.dumps(final),f'conversation-attempt:{ident}:{req.response_id}'),ident,req.response_id))
    api().audit(r['context_id'],'conversation_response_'+next_state,'Citizen reply processed for core',{'interrupt_id':ident,'kind':r['kind']})
    return final


@router.get('/interrupts/{ident}/response')
async def response(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=get(ident)
    if r['state']!='completed':raise HTTPException(409,'No completed citizen response')
    if r['kind'] in ('otp','captcha'):return {'interrupt_id':ident,'context_id':r['context_id'],'generation':r['generation'],'state':'completed','secret_persisted':False}
    return {'interrupt_id':ident,'context_id':r['context_id'],'generation':r['generation'],**(json.loads(unseal(r['response'],f'interrupt-response:{ident}')) if r['response'] else {'state':'completed'})}


@router.post('/interrupts/{ident}/cancel')
async def cancel(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=get(ident)
    with api().conn() as db:
        if not db.execute("UPDATE conversation_interrupts SET state='cancelled' WHERE id=? AND state='pending'",(ident,)).rowcount:raise HTTPException(409,'Request cannot be cancelled in current state')
        db.execute("UPDATE conversation_deliveries SET state='cancelled' WHERE interrupt_id=? AND state IN ('queued','leased')",(ident,))
    if r['child_task']:
        from server.integration import cancel_task
        await cancel_task(r['child_task'],api().KEY)
    return {'state':'cancelled'}


@router.get('/executions/{ident}')
async def binding(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=execution(ident)
    return {'context_id':ident,'generation':r['generation'],'subject':r['subject'],'execution_type':r['type']}


@router.post('/interrupts/{ident}/reconcile')
async def reconcile(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=get(ident)
    if r['state']!='needs_reconciliation':return {'state':r['state']}
    state='cancelled'
    if r['kind'] in ('otp','captcha'):
        current=execution(r['context_id'])
        if current['type']!='adapter' or current['generation']!=r['generation']:raise HTTPException(409,'An old-generation secret response cannot be replayed')
        observed=await api().worker('GET',f'/sessions/{current["row"]["worker_id"]}/snapshot')
        if (r['kind']=='otp' and observed['stage']=='challenge') or (r['kind']=='captcha' and observed['stage']=='form'):
            state='completed'
            api().update(r['context_id'],state='captcha_needed' if r['kind']=='otp' else 'form_ready')
    with api().conn() as db:
        db.execute('UPDATE conversation_interrupts SET state=? WHERE id=?',(state,ident))
        db.execute("UPDATE conversation_deliveries SET state='cancelled' WHERE interrupt_id=? AND state IN ('queued','leased')",(ident,))
    return {'state':state,'fresh_request_required':state=='cancelled','secret_replayed':False}


def purge_context(context_id):
    initialize()
    with api().conn() as db:
        db.execute('DELETE FROM conversation_responses WHERE interrupt_id IN (SELECT id FROM conversation_interrupts WHERE context_id=?)',(context_id,))
        db.execute('DELETE FROM conversation_deliveries WHERE interrupt_id IN (SELECT id FROM conversation_interrupts WHERE context_id=?)',(context_id,))
        db.execute('DELETE FROM conversation_interrupts WHERE context_id=?',(context_id,))


@router.post('/notifications',status_code=201)
async def notify(req:Notification,x_internal_key:str|None=Header(None)):
    require(x_internal_key);expire();current=execution(req.context_id)
    if req.subject!=current['subject'] or req.generation!=current['generation']:raise HTTPException(409,'Notification recipient/generation mismatch')
    proof=None
    if req.kind in ('result','status'):
        if current['type']!='adapter':raise HTTPException(501,'A verified receipt/status adapter is required for a result notification')
        r=current['row']
        if r['state']!='submitted' or not req.receipt_ref or req.receipt_ref!=r['receipt_id']:raise HTTPException(409,'Notification must reference the observed application receipt')
        proof=await api().poll(req.context_id) if req.kind=='status' else {'receipt_id':r['receipt_id'],'portal':'fictional-demo'}
    from server.artifacts import read
    for ident in req.artifact_ids:read(req.context_id,ident)
    fingerprint=hashlib.sha256(req.model_dump_json().encode()).hexdigest();ident=str(uuid.uuid4());delivery=str(uuid.uuid4());now=time.time()
    payload={'version':'2','delivery_id':delivery,'notification_id':req.notification_id,'context_id':req.context_id,'generation':req.generation,'subject':req.subject,'kind':req.kind,'summary':req.summary,'receipt_ref':req.receipt_ref,'proof':proof,'artifact_ids':req.artifact_ids,'synthetic_runtime':True,'expires_at':now+1800,'requires_response':False}
    with api().conn() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT id,fingerprint FROM conversation_interrupts WHERE request_id=?',(req.notification_id,)).fetchone()
        if old:
            if old['fingerprint']!=fingerprint:raise HTTPException(409,'Notification ID changed')
            return {'notification_id':req.notification_id,'replayed':True}
        db.execute('INSERT INTO conversation_interrupts(id,request_id,fingerprint,context_id,generation,subject,kind,state,request,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,req.notification_id,fingerprint,req.context_id,req.generation,req.subject,'notification','notification_ready',seal(req.model_dump_json(),f'interrupt:{ident}'),now,now+1800))
        db.execute('INSERT INTO conversation_deliveries(id,interrupt_id,state,payload,created,expires) VALUES(?,?,?,?,?,?)',(delivery,ident,'queued',seal(json.dumps(payload),f'delivery:{delivery}'),now,now+1800))
    return {'notification_id':req.notification_id,'delivery_id':delivery,'replayed':False}
