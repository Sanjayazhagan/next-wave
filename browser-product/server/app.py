"""Control API and bundled fictional scholarship portal for Forge '26 demo.
Production use is intentionally disabled until identity, legal and portal authorization work is complete.
"""
import asyncio, base64, hashlib, hmac, io, json, os, secrets, sqlite3, time, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.pdfgen.canvas import Canvas
from server.contracts import PreparedDocument
from server.storage import seal, unseal

ROOT = Path(__file__).resolve().parent.parent
MODE = os.getenv('APP_MODE','demo')
DB = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'demo.db')))
WORKER = os.getenv('WORKER_URL','http://127.0.0.1:8101').rstrip('/')
MOCK = os.getenv('MOCK_BASE_URL','http://127.0.0.1:8100').rstrip('/')
KEY = os.getenv('INTERNAL_KEY','demo-worker-key-change-before-production')
SIGN_KEY = os.getenv('APP_SIGNING_KEY','demo-signing-key-change-before-production')
DEFAULT_PROFILE = {'student_name':'Kavya Demo', 'course':'B.Tech', 'income':'120000','state':'Tamil Nadu','category':'BC'}
ALLOWED_STATES = {'otp_needed','captcha_needed','form_ready','approval_needed','submitted','human_takeover','error'}

@asynccontextmanager
async def lifespan(app):
    if DB.exists():
        with sqlite3.connect(f'file:{DB.resolve().as_posix()}?mode=ro',uri=True) as existing:
            if existing.execute('PRAGMA user_version').fetchone()[0]>2:
                raise RuntimeError('Database schema is newer than this application; refusing downgrade')
    if MODE not in ('demo','integrated'):
        raise RuntimeError('APP_MODE must be demo or integrated')
    if MODE == 'integrated':
        if os.getenv('SECURITY_MODE') != 'signed':
            raise RuntimeError('Integrated mode requires SECURITY_MODE=signed')
        from browser.public_web import navigation_mode, NAV_MODE_PUBLIC
        if navigation_mode() != NAV_MODE_PUBLIC and (not os.getenv('BROWSER_ALLOWED_ORIGINS') or not os.getenv('BROWSER_PORTALS_JSON')):
            raise RuntimeError('Allowlist mode requires operator-reviewed origins and portal registry')
        from server.storage import cipher
        cipher()
    if os.getenv('SECURITY_MODE') == 'signed':
        identity_key = os.getenv('IDENTITY_SIGNING_KEY','')
        if len(identity_key) < 32 or identity_key in (KEY, SIGN_KEY):
            raise RuntimeError('Signed mode requires an independent identity key of at least 32 characters')
        if len(KEY) < 32 or len(SIGN_KEY) < 32 or KEY.startswith('demo-') or SIGN_KEY.startswith('demo-') or KEY == SIGN_KEY:
            raise RuntimeError('Signed mode refuses default, short or shared service/signing keys')
    if os.getenv('SECURITY_MODE') == 'signed':
        from server.storage import cipher
        cipher()
    elif os.getenv('DATA_ENCRYPTION_KEYS'):
        from server.storage import cipher
        cipher()
    DB.parent.mkdir(parents=True,exist_ok=True)
    db = conn()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sessions (
       id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, state TEXT NOT NULL, profile TEXT NOT NULL,
       consent_at TEXT NOT NULL, review_hash TEXT, receipt_id TEXT, repairs INTEGER DEFAULT 0,
       created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit (
       id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
       type TEXT NOT NULL, summary TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS audit_sid ON audit(session_id,id);
    CREATE TABLE IF NOT EXISTS demo_receipts (
       receipt_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
       status TEXT NOT NULL, created_at TEXT NOT NULL
    );
    ''')
    db.commit(); db.close()
    from server.integration import initialize as initialize_core
    from server.artifacts import initialize as initialize_artifacts
    from server.security import initialize_access
    initialize_core();initialize_artifacts();initialize_access()
    with conn() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]>2:
            raise RuntimeError('Database schema is newer than this application; refusing unsafe downgrade')
        db.execute('PRAGMA user_version=2')
    from server.maintenance import loop
    import sys
    maintenance = asyncio.create_task(loop(sys.modules[__name__]))
    try:
        yield
    finally:
        maintenance.cancel()
        try:
            await maintenance
        except asyncio.CancelledError:
            pass

app=FastAPI(title='GradientZero Browser & Product API', version='1.1.0', lifespan=lifespan)
from server.integration import router as integration_router
app.include_router(integration_router)
from server.artifacts import router as artifact_router
app.include_router(artifact_router)
from server.access import router as access_router
app.include_router(access_router)
from server.browser_v2 import router as browser_v2_router
app.include_router(browser_v2_router)
from server.core_gateway import router as core_gateway_router
app.include_router(core_gateway_router)
from server.core_assist import router as core_assist_router
app.include_router(core_assist_router)
from server.browser_lab import router as browser_lab_router
app.include_router(browser_lab_router)
from server.conversation_bridge import router as conversation_router
app.include_router(conversation_router)

@app.middleware('http')
async def human_task_guard(request, call_next):
    from server.security import enforce
    try:
        request.state.identity = enforce(request)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    # The synthetic portal and synthetic receipt API must not be publicly
    # mistaken for a live government application in integrated mode.
    if MODE == 'integrated' and (request.url.path.startswith(('/mock','/api/sessions','/api/mock','/session','/browser-lab')) or request.url.path == '/'):
        return JSONResponse({'detail':'Synthetic demo routes are disabled in integrated mode'},status_code=404)
    # Assistance owns the challenge while claimed; legacy demo callers cannot race it.
    length = request.headers.get('content-length', '')
    if length and (not length.isdigit() or int(length) > 2*1024*1024):
        return JSONResponse({'detail':'Request body exceeds service limit'}, status_code=413)
    if request.url.path.startswith('/assist-api/') and request.method == 'POST':
        bucket = int(time.time()//60)
        client = hashlib.sha256((SIGN_KEY+str(request.client.host if request.client else 'unknown')).encode()).hexdigest()
        with conn() as db:
            db.execute('CREATE TABLE IF NOT EXISTS request_limits (client TEXT, bucket INTEGER, count INTEGER, PRIMARY KEY(client,bucket))')
            db.execute('DELETE FROM request_limits WHERE bucket<?', (bucket-2,))
            db.execute('INSERT INTO request_limits VALUES(?,?,1) ON CONFLICT(client,bucket) DO UPDATE SET count=count+1', (client,bucket))
            count = db.execute('SELECT count FROM request_limits WHERE client=? AND bucket=?', (client,bucket)).fetchone()['count']
        if count > 120:
            return JSONResponse({'detail':'Too many verification actions; retry shortly'}, status_code=429, headers={'Retry-After':'60'})
    parts = request.url.path.strip('/').split('/')
    if request.method == 'POST' and ((len(parts) >= 4 and parts[:2] == ['api', 'sessions']) or (len(parts) >= 3 and parts[0] == 'session')):
        sid_index = 2 if parts[0] == 'api' else 1
        from server.integration import initialize
        initialize()
        with conn() as db:
            pending = db.execute("SELECT id FROM human_tasks WHERE session_id=? AND state IN ('offered','claimed','answering') AND expires>?", (parts[sid_index], time.time())).fetchone()
        if pending and parts[sid_index+1] != 'resume':
            return JSONResponse({'detail': 'Human verification owns this browser step'}, status_code=409)
        from server.conversation_bridge import active
        if active(parts[sid_index]):
            return JSONResponse({'detail':'Core conversation reply is pending; resolve it before browser mutation'},status_code=409)
    lease = None
    if request.method in ('POST', 'DELETE') and ((len(parts) >= (3 if request.method=='DELETE' else 4) and parts[:2] == ['api', 'sessions']) or (len(parts) >= 3 and parts[0] == 'session')):
        lease_sid = parts[2] if parts[0] == 'api' else parts[1]
        lease = str(uuid.uuid4())
        with conn() as db:
            db.execute('CREATE TABLE IF NOT EXISTS execution_leases (session_id TEXT PRIMARY KEY, token TEXT NOT NULL, expires REAL NOT NULL)')
            db.execute('DELETE FROM execution_leases WHERE expires < ?', (time.time(),))
            changed = db.execute('INSERT OR IGNORE INTO execution_leases VALUES (?,?,?)', (lease_sid, lease, time.time()+120)).rowcount
        if not changed:
            return JSONResponse({'detail': 'Session action is already in progress'}, status_code=409)
    try:
        response = await call_next(request)
    finally:
        if lease:
            with conn() as db:
                db.execute('DELETE FROM execution_leases WHERE token=?', (lease,))
    if request.url.path.startswith(('/assist', '/core-assist', '/core-browser/', '/integration/','/api/','/auth/')):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

class Start(BaseModel):
    consent: bool = Field(strict=True)
    portal: str = 'mock-scholarship'
    profile: dict = Field(default_factory=lambda: dict(DEFAULT_PROFILE))

class Otp(BaseModel):
    otp: str = Field(min_length=1,max_length=32)

class Human(BaseModel):
    challenge_answer: str = Field(min_length=1,max_length=30)

class Chaos(BaseModel):
    script_name: str
    options: dict = Field(default_factory=dict)

class Approve(BaseModel):
    review_hash: str
    confirmed: bool = Field(strict=True)

class EditProfile(BaseModel):
    profile: dict

class Action(BaseModel):
    kind: str
    target: str = ''
    value: str = ''
    strategy: str = 'label'
    timeout_ms: int = 5000


def now(): return datetime.now(timezone.utc).isoformat()
def conn():
    c=sqlite3.connect(DB,timeout=10,check_same_thread=False)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c

def row(sid):
    with conn() as c:
        r=c.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
    if r is None: raise HTTPException(404,'Session does not exist')
    result=dict(r)
    result['profile']=unseal(result['profile'],f'profile:{sid}')
    return result

def update(sid, **values):
    if not values: return
    if 'profile' in values:
        values['profile']=seal(values['profile'],f'profile:{sid}')
    values['updated_at']=now()
    with conn() as c:
        c.execute('UPDATE sessions SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?', (*values.values(), sid))
        c.commit()

def audit(sid,typ,summary,data=None):
    # Privacy: only event types / field names / no OTPs / no profile or raw documents.
    with conn() as c:
        c.execute('INSERT INTO audit (session_id,type,summary,data,at) VALUES (?,?,?,?,?)',
                  (sid,typ,summary,json.dumps(data or {},ensure_ascii=False),now()))
        c.commit()

async def worker(method,path,payload=None,timeout=20):
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, headers={'X-Internal-Key':KEY}) as client:
        try:
            res = await client.request(method,WORKER+path,json=payload)
        except httpx.ConnectError:
            raise HTTPException(503,'Browser worker is offline. Start both services using scripts/run_local.py.')
        except httpx.TimeoutException:
            raise HTTPException(504,'Browser worker timed out')
        if res.status_code >= 400:
            try: detail=res.json().get('detail','Browser action failed')
            except Exception: detail='Browser action failed'
            raise HTTPException(res.status_code,str(detail)[:180],headers={**({'X-Browser-Outcome':res.headers['x-browser-outcome']} if res.headers.get('x-browser-outcome') in ('not_applied','unknown') else {}),**({'Retry-After':str(min(60,max(0,int(res.headers['retry-after']))))} if res.headers.get('retry-after','').isdigit() else {})})
        return res.json()

def public(r):
    return {k:r[k] for k in ('id','state','receipt_id','review_hash','repairs','created_at','updated_at')}

@app.get('/health')
async def health():
    return {'ok':True,'mode':MODE,'product':'GradientZero / CivicFlow','real_portal_enabled':False}

@app.get('/')
async def index(): return FileResponse(ROOT/'web'/'index.html')
@app.get('/app.css')
async def css(): return FileResponse(ROOT/'web'/'app.css',media_type='text/css')
@app.get('/app.js')
async def js(): return FileResponse(ROOT/'web'/'app.js',media_type='application/javascript')

@app.get('/mock/')
@app.get('/mock')
async def mock_portal(): return FileResponse(ROOT/'web'/'mock.html')

@app.post('/mock/api/submit')
async def mock_submit(payload:dict):
    key=payload.get('idempotency_key')
    if not isinstance(key,str) or len(key)>100 or len(key)<8:
        raise HTTPException(400,'Mock idempotency key required')
    with conn() as c:
        existing=c.execute('SELECT receipt_id FROM demo_receipts WHERE idempotency_key=?',(key,)).fetchone()
        if existing: return {'receipt_id':existing['receipt_id'],'status':'submitted'}
        receipt='MOCK-2026-'+str(uuid.uuid4()).split('-')[0].upper()
        c.execute('INSERT INTO demo_receipts VALUES (?,?,?,?)',(receipt,key,'submitted',now()))
        c.commit()
        return {'receipt_id':receipt,'status':'submitted'}

@app.get('/mock/api/status/{receipt_id}')
async def mock_status(receipt_id:str):
    with conn() as c:
        r=c.execute('SELECT status, created_at FROM demo_receipts WHERE receipt_id=?',(receipt_id,)).fetchone()
    if not r: raise HTTPException(404,'Unknown mock receipt')
    return {'receipt_id':receipt_id,'status':r['status'],'checked_at':now(), 'portal':'fictional-demo'}

@app.post('/api/sessions')
@app.post('/session')
async def start(req:Start, request:Request=None):
    if not req.consent: raise HTTPException(400,'Explicit consent is required')
    if req.portal!='mock-scholarship': raise HTTPException(403,'Only the fictional mock portal is supported')
    profile={k:str(req.profile.get(k,'')).strip() for k in DEFAULT_PROFILE}
    if any(not value or len(value)>100 for value in profile.values()): raise HTTPException(400,'All five synthetic profile fields required')
    if not profile['income'].isdigit(): raise HTTPException(400,'Income should be a numeric string')
    sid=str(uuid.uuid4())
    created=await worker('POST','/sessions',{'target_url':MOCK+'/mock/','submission_key':sid},timeout=30)
    with conn() as c:
        c.execute('INSERT INTO sessions(id,worker_id,state,profile,consent_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                  (sid,created['worker_session_id'],'otp_needed',seal(json.dumps(profile),f'profile:{sid}'),now(),now(),now()))
        c.commit()
    if request is not None and getattr(request.state, 'identity', None):
        with conn() as c:
            c.execute('INSERT INTO session_owners VALUES (?,?)', (sid, request.state.identity['sub']))
    audit(sid,'consent','Demo processing consent received')
    audit(sid,'otp_needed','Waiting for citizen to enter mock OTP')
    return public(row(sid))

@app.get('/api/sessions/{sid}')
async def get_session(sid:str): return public(row(sid))

@app.get('/api/sessions/{sid}/fields')
async def fields(sid:str):
    r=row(sid)
    profile=json.loads(r['profile'])
    from server.integration import initialize
    initialize()
    with conn() as db:
        evidence=db.execute('SELECT fields FROM provenance WHERE session_id=?',(sid,)).fetchone()
    if evidence:
        return {'fields':[{'name':k, **v, 'source':v['source_ref']} for k,v in json.loads(unseal(evidence['fields'],f'provenance:{sid}')).items()]}
    return {'fields':[{'name':k,'value':v,'source':('synthetic citizen answer' if k!='income' else 'synthetic income certificate'), 'source_ref':'DEMO-FIXTURE','confidence':1.0} for k,v in profile.items()]}

@app.get('/api/sessions/{sid}/snapshot')
async def get_snapshot(sid:str):
    r=row(sid)
    return await worker('GET',f'/sessions/{r["worker_id"]}/snapshot')

@app.post('/api/sessions/{sid}/otp')
async def relay_otp(sid:str,req:Otp):
    r=row(sid)
    if r['state']!='otp_needed': raise HTTPException(409,'Not waiting for OTP')
    result=await worker('POST',f'/sessions/{r["worker_id"]}/otp',{'otp':req.otp})
    if result['ok']:
        update(sid,state='captcha_needed')
        audit(sid,'captcha_needed','Human-only mock challenge required')
    else: audit(sid,'otp_retry','Incorrect mock OTP (value never logged)')
    return {'state':row(sid)['state'],'ok':result['ok']}

@app.post('/api/sessions/{sid}/human')
async def challenge(sid:str,req:Human):
    r=row(sid)
    if r['state']!='captcha_needed': raise HTTPException(409,'Not waiting for human challenge')
    result=await worker('POST',f'/sessions/{r["worker_id"]}/human',{'challenge_answer':req.challenge_answer})
    if result['ok']:
        update(sid,state='form_ready')
        audit(sid,'form_ready','Human completed mock challenge')
    else: audit(sid,'challenge_retry','Mock challenge answer incorrect (value not logged)')
    return {'state':row(sid)['state'],'ok':result['ok']}

# In demo mode certificate upload is synthetic, no real user-upload storage.
def fixture_pdf():
    b=io.BytesIO(); p=Canvas(b,pagesize=(470,250))
    p.setFont('Helvetica-Bold',15); p.drawString(32,207,'SYNTHETIC CERTIFICATE - DEMO ONLY')
    p.setFont('Helvetica',11); p.drawString(32,174,'This document is fictional. No government authority issued it.')
    p.drawString(32,150,'Used for a non-production browser integration test.')
    p.save(); return b.getvalue()

@app.post('/api/sessions/{sid}/fill')
async def fill_form(sid:str, document:dict | None=None):
    r=row(sid)
    if r['state']!='form_ready': raise HTTPException(409,'Log in and complete human challenge first')
    req={'profile':json.loads(r['profile']), 'file_name':'synthetic-certificate.pdf','file_base64':base64.b64encode(fixture_pdf()).decode()}
    if document:
        if not isinstance(document, PreparedDocument):
            try:
                document = PreparedDocument.model_validate(document)
            except Exception:
                raise HTTPException(422, 'Invalid prepared document payload')
        from server.integration import initialize
        initialize()
        with conn() as db:
            owner = db.execute('SELECT subject FROM session_owners WHERE session_id=?',(sid,)).fetchone()
        if not owner or owner['subject'] != document.subject:
            raise HTTPException(403, 'Prepared document owner does not match this session')
        try:
            raw = base64.b64decode(document.file_base64,validate=True)
        except Exception:
            raise HTTPException(422, 'Invalid prepared document encoding')
        if len(raw)>1048576 or not raw.startswith(b'%PDF-'):
            raise HTTPException(422, 'Prepared document must be PDF, at most 1 MB for this adapter')
        req.update(file_name=document.file_name,file_base64=document.file_base64)
    result=await worker('POST',f'/sessions/{r["worker_id"]}/fill',req,timeout=35)
    for f in result.get('fields',[]):
        audit(sid,'field_filled','Field filled using '+f['method'],{'field':f['field'],'source':'DEMO-FIXTURE'})
    if result['stage']!='review_ready':
        update(sid,state='human_takeover')
        audit(sid,'human_takeover','After 3 attempts, the browser stopped at a human intervention',{'blocked_field':result.get('blocked_field')})
        return {'state':'human_takeover','repairs':result.get('repair_attempts',3)}
    actual={k:str(v) for k,v in result['actual'].items()}
    expected=json.loads(r['profile'])
    if any(actual.get(k)!=expected.get(k) for k in expected):
        update(sid,state='human_takeover')
        audit(sid,'review_mismatch','Portal review values disagree with verified profile')
        return {'state':'human_takeover','reason':'review_mismatch'}
    digest=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    update(sid,state='approval_needed',review_hash=digest,repairs=result.get('repairs',0))
    audit(sid,'approval_needed','Review passed; explicit citizen approval required',{'review_hash_prefix':digest[:10]})
    return {'state':'approval_needed','review_hash':digest,'repairs':result.get('repairs',0)}

@app.post('/api/sessions/{sid}/approve')
async def approve(sid:str,req:Approve):
    r=row(sid)
    if not req.confirmed: raise HTTPException(400,'Explicit affirmative approval required')
    if r['state']!='approval_needed' or not r['review_hash'] or req.review_hash!=r['review_hash']:
        raise HTTPException(409,'Approval invalid: review state or digest changed')
    exp=int(time.time()+90)
    message=f'{r["worker_id"]}:{r["review_hash"]}:{exp}'.encode()
    signature=hmac.new(SIGN_KEY.encode(),message,hashlib.sha256).hexdigest()
    # Audit approval first, then exclusively approved worker submit; retry requires inspecting receipt.
    update(sid, state='submission_uncertain')
    audit(sid,'approved','Citizen explicitly approved the reviewed fields')
    result=await worker('POST',f'/sessions/{r["worker_id"]}/submit',{'capability':f'{exp}.{signature}','review_hash':r['review_hash']},timeout=30)
    update(sid,state='submitted',receipt_id=result['receipt'])
    audit(sid,'submitted','Mock portal returned a synthetic application receipt',{'receipt_id':result['receipt']})
    return {'state':'submitted','receipt_id':result['receipt']}

@app.post('/api/sessions/{sid}/edit')
async def edit_review(sid: str, req: EditProfile):
    r = row(sid)
    if r['state'] != 'approval_needed':
        raise HTTPException(409, 'Only an unsubmitted review can be edited')
    profile = {k: str(req.profile.get(k, '')).strip() for k in DEFAULT_PROFILE}
    if any(not v or len(v) > 100 for v in profile.values()) or not profile['income'].isdigit():
        raise HTTPException(400, 'Provide all five fields with a numeric income')
    await worker('POST', f'/sessions/{r["worker_id"]}/edit')
    update(sid, profile=json.dumps(profile), state='form_ready', review_hash=None)
    from server.integration import initialize
    initialize()
    with conn() as db:
        db.execute('UPDATE provenance SET fields=? WHERE session_id=?', (seal(json.dumps({k:{'value':v,'source_ref':'citizen-approved-edit','confidence':1.0,'verified':True} for k,v in profile.items()}),f'provenance:{sid}'),sid))
    audit(sid, 'review_edited', 'Citizen revised the test profile; fresh review and approval required')
    return public(row(sid))

@app.post('/api/sessions/{sid}/resume')
async def resume(sid: str):
    r = row(sid)
    if r['state'] == 'submitted':
        return public(r)
    if r['state'] == 'submission_uncertain':
        raise HTTPException(409, 'Submission outcome must be reconciled before browser recovery')
    try:
        await worker('GET', f'/sessions/{r["worker_id"]}/snapshot')
        return public(r)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    created = await worker('POST', '/sessions', {'target_url': MOCK+'/mock/', 'submission_key': sid}, timeout=30)
    update(sid, worker_id=created['worker_session_id'], state='otp_needed', review_hash=None)
    audit(sid, 'browser_restarted', 'Browser context was lost. Saved profile retained; human login and fresh review required')
    return public(row(sid))

@app.post('/api/sessions/{sid}/inject')
@app.post('/session/{sid}/inject')
async def inject(sid:str,req:Chaos):
    r=row(sid)
    if r['state'] in {'submitted','approval_needed'}: raise HTTPException(409,'Chaos cannot invalidate an approved review or submitted receipt')
    result=await worker('POST',f'/sessions/{r["worker_id"]}/inject',req.model_dump())
    if req.script_name=='expire_session':
        update(sid,state='otp_needed',review_hash=None)
        audit(sid,'session_expired','Mock portal session expired; checkpoint retained; re-login required')
    else: audit(sid,'chaos_injected','Named demo mutation activated',{'script':req.script_name})
    return result

@app.post('/api/sessions/{sid}/action')
async def action(sid:str,req:Action):
    r=row(sid)
    if r['state'] in {'submitted','approval_needed'}: raise HTTPException(403,'Actions blocked at final review/submission')
    result=await worker('POST',f'/sessions/{r["worker_id"]}/action',req.model_dump())
    audit(sid,'browser_action','Allowlisted semantic action executed',{'kind':req.kind})
    return result

@app.get('/api/sessions/{sid}/audit')
async def get_audit(sid:str,after:int=0):
    row(sid)
    with conn() as c:
        rs=c.execute('SELECT * FROM audit WHERE session_id=? AND id>? ORDER BY id LIMIT 300',(sid,after)).fetchall()
    return {'events':[dict(x)|{'data':json.loads(x['data'])} for x in rs]}

@app.get('/api/sessions/{sid}/events')
async def events(sid:str, after:int=0, last_event_id:str | None = Header(None)):
    row(sid)
    try:
        cursor=max(0, int(last_event_id)) if last_event_id else max(0, after)
    except ValueError:
        raise HTTPException(400, 'Invalid event cursor')
    async def iterator():
        last=cursor
        while True:
            with conn() as c:
                rs=c.execute('SELECT * FROM audit WHERE session_id=? AND id>? ORDER BY id LIMIT 30',(sid,last)).fetchall()
            for r in rs:
                last=r['id']
                payload={'id':r['id'],'type':r['type'],'summary':r['summary'],'at':r['at'],'data':json.loads(r['data'])}
                yield 'id: '+str(last)+'\ndata: '+json.dumps(payload)+'\n\n'
            yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(iterator(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/sessions/{sid}/poll')
async def poll(sid:str):
    r=row(sid)
    if r['state']!='submitted': raise HTTPException(409,'Only submitted demo applications have a status')
    async with httpx.AsyncClient(timeout=5) as client:
        res=await client.get(MOCK+'/mock/api/status/'+r['receipt_id'])
        res.raise_for_status()
        out=res.json()
    audit(sid,'status_checked','Fictional portal status checked',{'status':out['status']})
    return out

@app.get('/api/sessions/{sid}/receipt.pdf')
async def receipt_pdf(sid:str):
    r=row(sid)
    if r['state']!='submitted': raise HTTPException(409,'Receipt only available after submission')
    b=io.BytesIO(); pdf=Canvas(b,pagesize=(595,842))
    pdf.setFont('Helvetica-Bold',19);pdf.drawString(45,770,'GRADIENTZERO - DEMO RECEIPT')
    pdf.setFont('Helvetica-Bold',12);pdf.drawString(45,730,'FICTIONAL PORTAL / NOT GOVERNMENT-ISSUED')
    pdf.setFont('Helvetica',12);pdf.drawString(45,690,'Application reference: '+r['receipt_id'])
    pdf.drawString(45,670,'Submission status: SIMULATED / SUCCESS')
    pdf.drawString(45,625,'This is a mock receipt for a hackathon demonstration.')
    pdf.save()
    return Response(b.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{r["receipt_id"]}.pdf"'})

@app.delete('/api/sessions/{sid}')
async def delete(sid:str):
    r=row(sid)
    await worker('DELETE',f'/sessions/{r["worker_id"]}')
    from server.conversation_bridge import purge_context
    purge_context(sid)
    with conn() as c:
        for table in ('audit','human_tasks','session_owners','provenance','core_commands','artifacts','operator_assignments'):
            c.execute(f'DELETE FROM {table} WHERE session_id=?',(sid,))
        c.execute('DELETE FROM core_requests WHERE session_id=?',(sid,))
        c.execute('DELETE FROM demo_receipts WHERE idempotency_key=?',(sid,))
        c.execute('DELETE FROM sessions WHERE id=?',(sid,))
        c.commit()
    return {'ok':True}


@app.get('/assist.js')
async def assist_js():
    return FileResponse(ROOT/'web'/'assist.js', media_type='application/javascript')

@app.get('/assist.css')
async def assist_css():
    return FileResponse(ROOT/'web'/'assist.css', media_type='text/css')


@app.get('/ready')
async def ready():
    with conn() as db:
        db.execute('SELECT 1').fetchone()
    browser = await worker('GET', '/ready')
    return {'ok': True, 'mode': MODE, 'browser_connected': browser['ok']}

@app.post('/api/sessions/{sid}/human-task')
async def demo_human_task(sid: str):
    from server.integration import create_task, TaskRequest
    return await create_task(TaskRequest(session_id=sid), KEY)

@app.get('/api/sessions/{sid}/human-tasks')
async def session_tasks(sid: str):
    row(sid)
    from server.integration import initialize
    initialize()
    with conn() as db:
        result = db.execute('SELECT id,state,expires,attempts FROM human_tasks WHERE session_id=? ORDER BY expires DESC LIMIT 20', (sid,)).fetchall()
    return {'tasks':[dict(r) for r in result]}

from server.boundary import RequestBoundary
from server.rate_limit import RateLimit
app.add_middleware(RateLimit)
app.add_middleware(RequestBoundary)
from server.telemetry import Telemetry
app.add_middleware(Telemetry)
from starlette.middleware.trustedhost import TrustedHostMiddleware
app.add_middleware(TrustedHostMiddleware,allowed_hosts=[h.strip() for h in os.getenv('ALLOWED_HOSTS','127.0.0.1,localhost,testserver').split(',') if h.strip()])

@app.get('/browser-workbench')
async def browser_workbench():return FileResponse(ROOT/'web'/'browser_workbench.html')

@app.get('/browser-workbench.js')
async def browser_workbench_js():return FileResponse(ROOT/'web'/'browser_workbench.js',media_type='application/javascript')

@app.get('/api/browser-contexts/{ident}/view')
async def browser_context_view(ident:str):
    from server.browser_v2 import view
    return await view(ident,KEY)


@app.post('/api/sessions/{sid}/reconcile')
async def reconcile(sid: str):
    r = row(sid)
    if r['state'] != 'submission_uncertain':
        return public(r)
    # This query is authoritative only for the bundled fictional portal.
    with conn() as db:
        receipt = db.execute('SELECT receipt_id FROM demo_receipts WHERE idempotency_key=?', (sid,)).fetchone()
    if receipt:
        update(sid, state='submitted', receipt_id=receipt['receipt_id'])
        audit(sid, 'submission_reconciled', 'Fictional portal confirmed the existing receipt')
        return public(row(sid))
    # No negative inference: a timeout may have happened before/after the portal commit.
    raise HTTPException(409, 'No confirmed receipt. Human/core reconciliation required; automatic resubmission blocked')
