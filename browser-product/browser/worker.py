"""Internal Playwright browser worker. Demo-only target allowlist, isolated contexts.
All real portals must have explicit written permission and separately implemented adapters.
"""
import asyncio, base64, hashlib, hmac, json, os, re, time, uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import urlparse
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from browser.adapters import MOCK as adapter
from browser.public_web import navigation_mode, NAV_MODE_PUBLIC

MODE = os.getenv('APP_MODE', 'demo')
MOCK_URL = os.getenv('MOCK_BASE_URL', 'http://127.0.0.1:8100').rstrip('/')
INTERNAL_KEY = os.getenv('INTERNAL_KEY', 'demo-worker-key-change-before-production')
SIGN_KEY = os.getenv('APP_SIGNING_KEY', 'demo-signing-key-change-before-production')
CHROMIUM_PATH = os.getenv('CHROMIUM_PATH', '')

@dataclass
class Session:
    context: object
    page: object
    created: float = field(default_factory=time.time)
    repairs: int = 0
    stage: str = 'new'
    used_caps: set = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    challenge_frame: str = ''
    challenge_box: dict = field(default_factory=dict)
    challenge_frame_at: float = 0
    last_used: float = field(default_factory=time.time)

sessions: dict[str, Session] = {}
creation_lock = asyncio.Lock()

async def reap_idle():
    while True:
        await asyncio.sleep(60)
        cutoff = time.time()-int(os.getenv('MAX_BROWSER_IDLE_SECONDS','900'))
        from browser.general_routes import contexts
        for ident,context in list(contexts.items()):
            if context.last_used<cutoff and not context.lock.locked():
                async with context.lock:
                    if context.last_used<cutoff:
                        contexts.pop(ident,None);await context.context.close()
                        from browser.core_compat import bridges
                        for bridge_id,info in list(bridges.items()):
                            if info.context_id==ident:bridges.pop(bridge_id,None)
        for sid, session in list(sessions.items()):
            if session.last_used < cutoff and not session.lock.locked():
                async with session.lock:
                    if session.last_used < cutoff and sessions.get(sid) is session:
                        sessions.pop(sid, None)
                        await session.context.close()

@asynccontextmanager
async def lifespan(app):
    if MODE not in ('demo','integrated'):
        raise RuntimeError('APP_MODE must be demo or integrated')
    if MODE=='integrated' and navigation_mode() != NAV_MODE_PUBLIC and (not os.getenv('BROWSER_ALLOWED_ORIGINS') or not os.getenv('BROWSER_PORTALS_JSON')):
        raise RuntimeError('Allowlist mode requires explicit origins and portal registry')
    if not INTERNAL_KEY or not SIGN_KEY:
        raise RuntimeError('Internal keys required')
    p = await async_playwright().start()
    browser_args = ['--no-sandbox', '--disable-dev-shm-usage']
    # Optional workaround for websites whose parser-blocking scripts stall over HTTP/2.
    if os.getenv('CHROMIUM_DISABLE_HTTP2', 'false').strip().lower() in ('1', 'true', 'yes', 'on'):
        browser_args.append('--disable-http2')
    options = dict(headless=True, args=browser_args)
    if CHROMIUM_PATH:
        options['executable_path'] = CHROMIUM_PATH
    browser = await p.chromium.launch(**options)
    app.state.browser = browser
    reaper = asyncio.create_task(reap_idle())
    try:
        yield
    finally:
        reaper.cancel()
        try:
            await reaper
        except asyncio.CancelledError:
            pass
        for s in list(sessions.values()):
            await s.context.close()
        sessions.clear()
        from browser.general_routes import contexts
        for context in list(contexts.values()):await context.context.close()
        contexts.clear()
        await browser.close()
        await p.stop()

app = FastAPI(title='GradientZero Internal Browser Worker', lifespan=lifespan, docs_url=None, redoc_url=None)
from browser.general_routes import router as general_router
app.include_router(general_router)
from browser.core_compat import router as core_compat_router
app.include_router(core_compat_router)

def require_key(x_internal_key: str | None):
    if not x_internal_key or not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(401, 'Internal worker authentication required')

def sget(sid: str):
    s = sessions.get(sid)
    if not s: raise HTTPException(404, 'No browser session')
    s.last_used = time.time()
    return s

class CreateRequest(BaseModel):
    target_url: str
    submission_key: str = Field(default='', max_length=100)

class OtpRequest(BaseModel):
    otp: str = Field(min_length=1, max_length=32)

class HumanRequest(BaseModel):
    challenge_answer: str = Field(min_length=1, max_length=30)

class FillRequest(BaseModel):
    profile: dict
    file_name: str = 'synthetic-certificate.pdf'
    file_base64: str = ''

class InjectRequest(BaseModel):
    script_name: str
    options: dict = Field(default_factory=dict)

class SubmitRequest(BaseModel):
    capability: str
    review_hash: str

class ActionRequest(BaseModel):
    kind: str
    strategy: str = 'label'
    target: str = ''
    value: str = ''
    timeout_ms: int = Field(default=5000, ge=100, le=15000)

class HumanControl(BaseModel):
    kind: str
    frame_id: str
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    text: str = Field(default='', max_length=100)
    key: str = ''

async def page_phase(page):
    try:
        return await adapter.phase(page)
    except Exception:
        return 'unknown'

async def allowed_route(route):
    """Fail closed for non-demo destinations, including network subresources and redirects."""
    target = urlparse(route.request.url)
    allowed = urlparse(MOCK_URL)
    if (target.scheme, target.hostname, target.port) != (allowed.scheme, allowed.hostname, allowed.port):
        return await route.abort('blockedbyclient')
    return await route.continue_()

@app.get('/health')
async def health(): return {'ok': True, 'mode': MODE}

@app.post('/sessions')
async def create(req: CreateRequest, x_internal_key: str | None = Header(None)):
    async with creation_lock:
        require_key(x_internal_key)
        target = urlparse(req.target_url)
        allowed = urlparse(MOCK_URL)
        if (target.scheme, target.hostname, target.port) != (allowed.scheme, allowed.hostname, allowed.port) or target.path not in ('/mock', '/mock/'):
            raise HTTPException(400, 'Only the bundled mock portal is allowlisted')
        from browser.general_routes import contexts
        if len(sessions)+len(contexts) >= int(os.getenv('MAX_BROWSER_SESSIONS', '8')):
            raise HTTPException(429, 'Browser capacity reached; retry after an existing session closes')
        context = await app.state.browser.new_context(viewport={'width': 1180, 'height': 760}, device_scale_factor=1, accept_downloads=False)
        try:
            await context.route('**/*', allowed_route)
            page = await context.new_page()
            await page.goto(MOCK_URL + '/mock/', wait_until='domcontentloaded')
            if req.submission_key:
                await page.evaluate('(key)=>sessionStorage.setItem(\"submission_key\",key)', req.submission_key)
            await page.get_by_role('button', name='Send login OTP').click()
        except Exception:
            await context.close()
            raise
        sid = str(uuid.uuid4())
        sessions[sid] = Session(context=context, page=page, stage='otp_needed')
        return {'worker_session_id': sid, 'stage': 'otp_needed'}

@app.get('/sessions/{sid}/snapshot')
async def snapshot(sid: str, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        stage = await page_phase(s.page)
        secret_fields = s.page.locator('input[autocomplete=off],input[type=password]')
        shot = await s.page.screenshot(type='jpeg', quality=54, animations='disabled', mask=[secret_fields])
        aria = await s.page.locator('body').aria_snapshot(timeout=6000)
        return {'stage': stage, 'url': s.page.url, 'title': await s.page.title(), 'accessibility': aria[:16000],
                'screenshot_base64': base64.b64encode(shot).decode(),
                'otp_needed': stage == 'otp', 'captcha_needed': stage == 'challenge',
                'error_detected': bool(await s.page.get_by_role('alert').count()), 'repairs': s.repairs}

@app.post('/sessions/{sid}/otp')
async def otp(sid: str, req: OtpRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        if await page_phase(s.page) != 'otp': raise HTTPException(409, 'OTP not required')
        await s.page.get_by_label('One-time code').fill(req.otp)
        await s.page.get_by_role('button', name='Verify OTP').click()
        stage = await page_phase(s.page)
        if stage != 'challenge':
            await s.page.get_by_label('One-time code').fill('')
            return {'stage': 'otp_needed', 'ok': False}
        s.stage = 'captcha_needed'
        return {'stage': s.stage, 'ok': True}

@app.post('/sessions/{sid}/human')
async def human(sid: str, req: HumanRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        if await page_phase(s.page) != 'challenge': raise HTTPException(409, 'Human challenge not required')
        await s.page.get_by_label('Human challenge answer').fill(req.challenge_answer)
        await s.page.get_by_role('button', name='Continue as human').click()
        stage = await page_phase(s.page)
        s.stage = 'form_ready' if stage == 'form' else 'captcha_needed'
        return {'stage': s.stage, 'ok': stage == 'form'}

async def fill_field(s: Session, primary: str, alt: str, value: str, key: str) -> str:
    try:
        await s.page.get_by_label(primary, exact=True).fill(str(value), timeout=1100)
        return 'saved-semantic-locator'
    except PWTimeout:
        aria = await s.page.locator('body').aria_snapshot(timeout=3000)
        if alt in aria:
            await s.page.get_by_label(alt, exact=True).fill(str(value), timeout=1200)
            s.repairs += 1
            return 'semantic-repair'
        # deterministic, scoped demo fallback; no arbitrary AI-driven mutations
        candidate = s.page.locator(f'[data-field="{key}"]')
        if await candidate.is_visible():
            await candidate.fill(str(value), timeout=1200)
            s.repairs += 1
            return 'test-id-repair'
        raise

@app.post('/sessions/{sid}/fill')
async def fill(sid: str, req: FillRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        if await page_phase(s.page) != 'form': raise HTTPException(409, 'Not on the form; re-login may be required')
        if await s.page.get_by_role('button', name='Dismiss notice').count():
            await s.page.get_by_role('button', name='Dismiss notice').click()
            s.repairs += 1
        events = []
        fields = adapter.fields
        for primary, alt, key in fields:
            value = req.profile.get(key)
            if value is None: raise HTTPException(400, 'Missing profile field')
            method = None
            # Three ACTUAL scoped re-evaluation attempts; never blindly fill a hidden field.
            for attempt in range(1,4):
                try:
                    method = await fill_field(s, primary, alt, value, key)
                    break
                except Exception:
                    await s.page.locator('body').aria_snapshot(timeout=3000)
                    if attempt < 3:
                        await asyncio.sleep(0.10 * attempt)
            if method is None:
                return {'stage': 'human_takeover', 'blocked_field': key, 'repair_attempts': 3, 'fields': events}
            events.append({'field': key, 'method': method})
        if req.file_base64:
            raw = base64.b64decode(req.file_base64, validate=True)
            if len(raw) > 1024 * 1024 or not raw.startswith(b'%PDF-'):
                raise HTTPException(400, 'Mock upload accepts only PDF <=1MB')
            await s.page.locator('input[type=file]').set_input_files({'name': req.file_name, 'mimeType':'application/pdf', 'buffer': raw})
        for attempt in range(3):
            await s.page.get_by_role('button', name='Continue to review').click()
            if await page_phase(s.page) == 'review': break
            await asyncio.sleep(0.15 * (attempt + 1))
        if await page_phase(s.page) != 'review':
            return {'stage': 'human_takeover', 'repair_attempts': 3, 'fields': events}
        actual = await adapter.review(s.page)
        s.stage = 'review_ready'
        return {'stage': 'review_ready', 'actual': actual, 'fields': events, 'repairs': s.repairs}

@app.post('/sessions/{sid}/inject')
async def inject(sid: str, req: InjectRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    if req.script_name not in {'rename_income','popup','expire_session','server_failure','hide_income','move_button'}:
        raise HTTPException(400, 'Unknown predefined chaos script')
    s = sget(sid)
    async with s.lock:
        await s.page.evaluate('(name) => window.demoInject(name)', req.script_name)
        if req.script_name == 'expire_session':
            await s.page.get_by_role('button', name='Send login OTP').click()
        return {'ok': True, 'script_name': req.script_name, 'stage': await page_phase(s.page)}

@app.post('/sessions/{sid}/edit')
async def edit(sid: str, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        if await page_phase(s.page) != 'review':
            raise HTTPException(409, 'Only an unsubmitted review can be edited')
        await s.page.get_by_role('button', name='Edit form', exact=True).click()
        s.stage = 'form_ready'
        return {'stage': s.stage}

@app.post('/sessions/{sid}/action')
async def action(sid: str, req: ActionRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    if req.kind not in {'fill','click','wait','snapshot'}: raise HTTPException(400, 'Unsafe action')
    if re.search(r'submit|approve|password|captcha|otp', req.target, re.I):
        raise HTTPException(403, 'Security and irreversible steps require dedicated human-gated endpoints')
    if req.strategy not in {'label','role_button'}: raise HTTPException(400, 'Only semantic locators accepted')
    async with s.lock:
        if req.kind in {'fill','click'} and await page_phase(s.page) != 'form':
            raise HTTPException(403, 'Generic mutations only operate on the application form')
        loc = s.page.get_by_label(req.target, exact=True) if req.strategy == 'label' else s.page.get_by_role('button', name=req.target, exact=True)
        if req.kind == 'fill': await loc.fill(req.value, timeout=req.timeout_ms)
        elif req.kind == 'click': await loc.click(timeout=req.timeout_ms)
        elif req.kind == 'wait': await asyncio.sleep(min(req.timeout_ms/1000, 2))
        return {'ok': True, 'stage': await page_phase(s.page)}

def expected_cap(sid, digest, exp):
    msg=f'{sid}:{digest}:{exp}'.encode()
    return hmac.new(SIGN_KEY.encode(), msg, hashlib.sha256).hexdigest()

@app.post('/sessions/{sid}/submit')
async def submit(sid: str, req: SubmitRequest, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        phase = await page_phase(s.page)
        if phase == 'receipt':
            receipt = await s.page.locator('[data-testid="receipt-id"]').inner_text()
            return {'stage':'submitted', 'receipt': receipt, 'already_submitted':True}
        if phase != 'review': raise HTTPException(409, 'Not at review stage')
        actual = await adapter.review(s.page)
        digest = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',',':')).encode()).hexdigest()
        if digest != req.review_hash: raise HTTPException(409, 'Review changed; fresh approval required')
        try: exp, proof = req.capability.split('.',1); exp = int(exp)
        except Exception: raise HTTPException(403, 'Invalid approval capability')
        if exp < time.time() or exp > time.time()+150 or proof in s.used_caps or not hmac.compare_digest(expected_cap(sid,digest,exp),proof):
            raise HTTPException(403, 'Approval absent, expired, or consumed')
        s.used_caps.add(proof)
        await s.page.get_by_role('button', name='Submit application').click()
        await s.page.locator('[data-testid="receipt-id"]').wait_for(timeout=8000)
        return {'stage':'submitted', 'receipt':await s.page.locator('[data-testid="receipt-id"]').inner_text(), 'already_submitted':False}

@app.delete('/sessions/{sid}')
async def destroy(sid: str, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sessions.get(sid)
    if s:
        async with s.lock:
            sessions.pop(sid,None)
            await s.context.close()
    return {'ok':True}


@app.get('/sessions/{sid}/challenge')
async def challenge_view(sid: str, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        phase = await page_phase(s.page)
        if phase != 'challenge':
            raise HTTPException(409, 'No supported human challenge is visible')
        shot = await s.page.locator('#main').screenshot(type='jpeg', quality=65)
        s.challenge_box = await s.page.locator('#main').bounding_box()
        s.challenge_frame = str(uuid.uuid4())
        s.challenge_frame_at = time.time()
        return {'stage': phase, 'mode': 'demo', 'interaction': 'text_answer',
                'frame_id': s.challenge_frame, 'controls': ['click', 'text', 'key'],
                'screenshot_base64': base64.b64encode(shot).decode(),
                'instructions': 'Answer the displayed synthetic challenge yourself.'}

@app.post('/sessions/{sid}/human-control')
async def human_control(sid: str, req: HumanControl, x_internal_key: str | None = Header(None)):
    require_key(x_internal_key)
    s = sget(sid)
    async with s.lock:
        if await page_phase(s.page) != 'challenge':
            raise HTTPException(409, 'Human control is restricted to the challenge step')
        if not req.frame_id or req.frame_id != s.challenge_frame or time.time()-s.challenge_frame_at > 30:
            raise HTTPException(409, 'Challenge frame is stale; refresh it')
        root = s.page.locator('#main')
        box = await root.bounding_box()
        if not box or box != s.challenge_box:
            raise HTTPException(409, 'Challenge geometry changed; refresh it')
        if req.kind == 'click':
            await s.page.mouse.click(box['x']+req.x*box['width'], box['y']+req.y*box['height'])
        elif req.kind in {'text', 'key'}:
            inside = await s.page.evaluate("document.querySelector('#main').contains(document.activeElement)")
            if not inside:
                raise HTTPException(403, 'Focus must be inside the challenge')
            if req.kind == 'text':
                editable = await s.page.evaluate("document.activeElement.matches('input:not([type=file]):not([type=password]),textarea')")
                if not editable:
                    raise HTTPException(403, 'Focus a challenge text field first')
                await s.page.keyboard.insert_text(req.text)
            else:
                if req.key not in {'Tab', 'Enter', 'Backspace', 'ArrowLeft', 'ArrowRight', 'Space'}:
                    raise HTTPException(400, 'Unsupported challenge key')
                await s.page.keyboard.press(req.key)
        else:
            raise HTTPException(400, 'Unsupported human action')
        s.challenge_frame = ''
        phase = await page_phase(s.page)
        return {'stage': phase, 'completed': phase == 'form'}


@app.get('/ready')
async def ready():
    healthy = bool(getattr(app.state, 'browser', None) and app.state.browser.is_connected())
    if not healthy:
        raise HTTPException(503, 'Chromium is not connected')
    return {'ok': True, 'mode': MODE, 'active_sessions': len(sessions)}
