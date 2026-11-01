"""Core/model-facing general browser gateway; no model/agent implementation."""
import base64
import json
import time
import uuid
from fastapi import APIRouter,Header,HTTPException
from browser.protocol import ContextStart,BrowserAction,ModelDecision,GeneralDocument,model_input,validate_decision
from server.storage import seal,unseal

router=APIRouter(prefix='/integration/v2/browser')

@router.get('/capabilities')
async def capabilities(x_internal_key:str|None=Header(None)):
    require(x_internal_key)
    from browser.extension_ports import capability_manifest
    return capability_manifest()


def api():
    from server import app
    return app


def initialize():
    with api().conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS browser_contexts(id TEXT PRIMARY KEY,request_id TEXT UNIQUE,request_hash TEXT NOT NULL,subject TEXT NOT NULL,worker_id TEXT,generation TEXT,state TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS browser_actions(context_id TEXT,action_id TEXT,fingerprint TEXT,state TEXT NOT NULL,result TEXT,PRIMARY KEY(context_id,action_id));
        ''')


def require(key):
    from server.integration import require_service
    require_service(key)
    from server.storage import cipher
    try:cipher()
    except (RuntimeError,ValueError):raise HTTPException(503,'Configure encrypted storage before using the general browser gateway')
    initialize()


def context(ident):
    with api().conn() as db:r=db.execute('SELECT * FROM browser_contexts WHERE id=?',(ident,)).fetchone()
    if not r:raise HTTPException(404,'No general browser execution context')
    return dict(r)


async def call(r,method,path,payload=None):
    if (r['state']!='active' and not (r['state']=='needs_reconciliation' and (method=='GET' or method=='DELETE'))) or not r['worker_id']:raise HTTPException(409,'Context requires explicit recreation and human reauthentication')
    try:return await api().worker(method,f'/contexts/{r["worker_id"]}'+path,payload,timeout=40)
    except HTTPException as exc:
        if exc.status_code==404:
            with api().conn() as db:db.execute("UPDATE browser_contexts SET state='lost' WHERE id=?",(r['id'],))
            raise HTTPException(409,'Browser context lost. Recreate with a new request ID; old observations, tabs and actions cannot be replayed')
        raise


@router.post('/contexts',status_code=201)
async def create(req:ContextStart,x_internal_key:str|None=Header(None)):
    require(x_internal_key)
    from server.integration import digest
    fingerprint=digest(json.dumps(req.model_dump(),sort_keys=True));ident=str(uuid.uuid4())
    with api().conn() as db:
        existing=db.execute('SELECT * FROM browser_contexts WHERE request_id=?',(req.request_id,)).fetchone()
        if existing:
            if existing['request_hash']!=fingerprint:raise HTTPException(409,'Request ID reused with different inputs')
            return {'id':existing['id'],'generation':existing['generation'],'state':existing['state'],'replayed':True}
        db.execute('INSERT INTO browser_contexts VALUES(?,?,?,?,NULL,NULL,?,?)',(ident,req.request_id,fingerprint,req.subject,'creating',time.time()))
    result=await api().worker('POST','/contexts',req.model_dump(),timeout=30)
    with api().conn() as db:
        db.execute("UPDATE browser_contexts SET worker_id=?,generation=?,state='active' WHERE id=?",(result['context_id'],result['generation'],ident))
        db.execute('INSERT INTO session_owners VALUES(?,?)',(ident,req.subject))
    api().audit(ident,'browser_context_created','General browser context created without a model or agent')
    return {'id':ident,'generation':result['generation'],'state':'active','observation':result}


@router.get('/contexts/{ident}/observe')
async def observation(ident:str,x_internal_key:str|None=Header(None),link_offset:int=0,link_query:str=''):
    require(x_internal_key)
    if not 0<=link_offset<=10000 or len(link_query)>120:raise HTTPException(422,'Invalid link query or offset')
    from urllib.parse import urlencode
    return await call(context(ident),'GET','/observe?'+urlencode({'link_offset':link_offset,'link_query':link_query}))

@router.get('/contexts/{ident}')
async def state(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=context(ident)
    return {k:r[k] for k in ('id','request_id','generation','state','created')}

@router.get('/contexts/{ident}/view')
async def view(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key)
    result=await call(context(ident),'GET','/view')
    with api().conn() as db:rows=db.execute("SELECT action_id,result FROM browser_actions WHERE context_id=? AND state='completed' ORDER BY rowid DESC LIMIT 20",(ident,)).fetchall()
    provenance=[]
    for row in rows:
        action=json.loads(unseal(row['result'],f'browser-action:{ident}:{row["action_id"]}'))
        if action.get('provenance'):provenance.append({'action_id':row['action_id'],**action['provenance']})
    result['provenance']=provenance
    return result


@router.get('/contexts/{ident}/events')
async def events(ident:str,after:int=0,x_internal_key:str|None=Header(None)):
    require(x_internal_key);context(ident)
    with api().conn() as db:rows=db.execute('SELECT id,type,summary,at FROM audit WHERE session_id=? AND id>? ORDER BY id LIMIT 100',(ident,max(0,after))).fetchall()
    return {'events':[dict(r) for r in rows],'next_cursor':rows[-1]['id'] if rows else after}


@router.post('/contexts/{ident}/actions')
async def action(ident:str,req:BrowserAction,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=context(ident)
    if r['state']!='active':raise HTTPException(409,'Context outcome requires reconciliation before any new action')
    from server.conversation_bridge import active
    if active(ident):raise HTTPException(409,'Citizen conversation response must be resolved before browser actions resume')
    from server.integration import digest
    fingerprint=digest(json.dumps(req.model_dump(),sort_keys=True));lease=str(uuid.uuid4())
    with api().conn() as db:
        db.execute('CREATE TABLE IF NOT EXISTS execution_leases(session_id TEXT PRIMARY KEY,token TEXT NOT NULL,expires REAL NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM conversation_interrupts WHERE context_id=? AND state IN ('pending','processing','needs_reconciliation')",(ident,)).fetchone():raise HTTPException(409,'Citizen reply is pending')
        previous=db.execute('SELECT * FROM browser_actions WHERE context_id=? AND action_id=?',(ident,req.action_id)).fetchone()
        if previous:
            if previous['fingerprint']!=fingerprint:raise HTTPException(409,'Action ID changed')
            if previous['state']=='rejected':
                error=json.loads(unseal(previous['result'],f'browser-action:{ident}:{req.action_id}'))
                raise HTTPException(error['status'],error['detail'],headers={'X-Browser-Outcome':'not_applied'})
            if previous['state']!='completed':raise HTTPException(409,'Previous action outcome unknown; observe instead of replaying')
            return {**json.loads(unseal(previous['result'],f'browser-action:{ident}:{req.action_id}')),'replayed':True}
        db.execute('DELETE FROM execution_leases WHERE expires<?',(time.time(),))
        if not db.execute('INSERT OR IGNORE INTO execution_leases VALUES(?,?,?)',(ident,lease,time.time()+60)).rowcount:raise HTTPException(409,'Another context action is in progress')
        db.execute('INSERT INTO browser_actions VALUES(?,?,?, ?,NULL)',(ident,req.action_id,fingerprint,'pending'))
    dispatched=False
    try:
        payload=req.model_dump()
        if req.kind=='upload':
            if not req.artifact_id:raise HTTPException(422,'An owner-bound artifact reference is required')
            from server.artifacts import read
            raw,metadata=read(ident,req.artifact_id)
            meta=json.loads(metadata)
            payload.update(file_base64=base64.b64encode(raw).decode(),file_name=meta['file_name'],file_mime=meta.get('mime_type','application/pdf'))
        dispatched=True
        result=await call(r,'POST','/actions',payload)
        with api().conn() as db:db.execute("UPDATE browser_actions SET state='completed',result=? WHERE context_id=? AND action_id=?",(seal(json.dumps(result),f'browser-action:{ident}:{req.action_id}'),ident,req.action_id))
        api().audit(ident,'browser_action_observed','General browser action completed',{'kind':req.kind})
        return result
    except HTTPException as exc:
        known=not dispatched or (exc.headers or {}).get('X-Browser-Outcome')=='not_applied'
        with api().conn() as db:
            if known:
                result=seal(json.dumps({'status':exc.status_code,'detail':str(exc.detail)}),f'browser-action:{ident}:{req.action_id}')
                db.execute("UPDATE browser_actions SET state='rejected',result=? WHERE context_id=? AND action_id=?",(result,ident,req.action_id))
            else:
                db.execute("UPDATE browser_actions SET state='unknown' WHERE context_id=? AND action_id=?",(ident,req.action_id))
                db.execute("UPDATE browser_contexts SET state='needs_reconciliation' WHERE id=? AND state='active'",(ident,))
        raise
    except BaseException:
        with api().conn() as db:
            db.execute("UPDATE browser_actions SET state='unknown' WHERE context_id=? AND action_id=?",(ident,req.action_id))
            if dispatched:db.execute("UPDATE browser_contexts SET state='needs_reconciliation' WHERE id=? AND state='active'",(ident,))
        raise
    finally:
        with api().conn() as db:db.execute('DELETE FROM execution_leases WHERE token=?',(lease,))


@router.post('/contexts/{ident}/model-input')
async def model_payload(ident:str,req:dict,x_internal_key:str|None=Header(None)):
    require(x_internal_key)
    goal=req.get('goal')
    if not isinstance(goal,str) or not 1<=len(goal)<=2000:raise HTTPException(422,'A trusted core goal is required')
    observed=await call(context(ident),'GET','/observe')
    return model_input(goal,observed)

@router.post('/contexts/{ident}/artifacts',status_code=201)
async def upload_artifact(ident:str,req:GeneralDocument,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=context(ident)
    if r['state']!='active':raise HTTPException(409,'Context is not active')
    from server.artifacts import upload
    return await upload(ident,req,x_internal_key)


@router.delete('/contexts/{ident}')
async def close(ident:str,x_internal_key:str|None=Header(None)):
    require(x_internal_key);r=context(ident)
    if r['state'] in ('active','needs_reconciliation'):
        try:await call(r,'DELETE','')
        except HTTPException as exc:
            if exc.status_code!=409:raise
    from server.conversation_bridge import purge_context
    purge_context(ident)
    with api().conn() as db:
        for table,column in [('browser_actions','context_id'),('artifacts','session_id'),('session_owners','session_id'),('audit','session_id')]:db.execute(f'DELETE FROM {table} WHERE {column}=?',(ident,))
        db.execute("UPDATE browser_contexts SET state='closed' WHERE id=?",(ident,))
    return {'state':'closed'}
