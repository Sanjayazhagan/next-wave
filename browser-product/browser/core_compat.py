"""Translate the existing next-wave LangGraph browser contract to live Playwright.

Lives on the PRIVATE worker at /core/session. The public browser API proxies this
under /core-browser/session with service authentication. This does not embed an
LLM: next-wave/app/planner.py makes every agent decision.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from browser.general import GeneralContext, observe, act, origin, signature
from browser.general_routes import contexts
from browser.protocol import BrowserAction

router = APIRouter(prefix='/core')

# Portal identifiers resolve ONLY to operator-provided, exact HTTPS URLs (or the
# local mock for test mode). No user-controlled URLs or selectors are accepted.
class Open(BaseModel):
    portal_id: str = Field(min_length=1, max_length=80)

class Login(BaseModel):
    portal_user_id: str = Field(min_length=1, max_length=200)

class Target(BaseModel):
    role: str
    name: str

class CoreAction(BaseModel):
    type: str
    target: Target | None = None
    value: str | None = None
    file_base64: str | None = None
    file_name: str | None = None
    file_mime: str | None = None
    wait_ms: int | None = None
    url: str | None = None

class Authorization(BaseModel):
    approved: bool
    approval_ref: str = Field(min_length=8, max_length=200)
    # Sent by the trusted core after the latest displayed review is approved.
    review_observation_id: str = Field(min_length=8, max_length=100)

@dataclass
class BridgeSession:
    context_id: str
    portal_id: str
    nodes: dict = field(default_factory=dict)   # (role,name) => element ref
    observation_id: str = ''
    fingerprint: str = ''
    approval: tuple | None = None             # (ref, observation id, expires)
    consumed: bool = False
    approval_refs: set[str] = field(default_factory=set)
    auth_target: str | None = None
    auth_value_entered: bool = False
    last_action: str = ''
    receipt_pattern: str | None = None

bridges: dict[str, BridgeSession] = {}


def worker():
    from browser import worker as w
    return w


def settings():
    try:
        entries = json.loads(os.getenv('BROWSER_PORTALS_JSON', '{}'))
    except json.JSONDecodeError:
        raise HTTPException(503, 'Invalid operator portal registry')
    if not isinstance(entries, dict):
        raise HTTPException(503, 'Portal registry must be an object')
    return entries


def get(sid):
    info = bridges.get(sid)
    if not info or info.context_id not in contexts:
        bridges.pop(sid, None)
        raise HTTPException(404, 'Core browser context was lost; reopen explicitly')
    return info, contexts[info.context_id]


def role_of(e):
    if e.get('role') in ('button','link','checkbox','textbox','combobox','radio','spinbutton'):
        return e['role']
    if e['tag'] == 'a': return 'link'
    if e['tag'] == 'button' or e['type'] in ('button','submit','reset','image'): return 'button'
    if e['type'] in ('checkbox','radio'): return e['type']
    if e['tag'] == 'select': return 'combobox'
    if e['type'] in ('number','range'): return 'spinbutton'
    return 'textbox'


def identify(e):
    # Use a stable accessible label, not a volatile DOM order or CSS selector.
    return e.get('label') or e.get('name') or e.get('type') or e.get('ref')


def human_kind(e):
    label = ' '.join(str(e.get(k, '')) for k in ('label','name','autocomplete','type'))
    if re.search(r'captcha|security.?code|human.?verification',label,re.I): return 'captcha'
    if re.search(r'otp|one.time|verification.?code|auth.?code',label,re.I): return 'otp'
    return None


def final_control(e):
    if e['risk'] != 'irreversible': return False
    return bool(re.search(r'\b(submit|finali[sz]e|send application|pay|apply now|confirm application)\b', identify(e), re.I))


def challenge_info(obs, nodes):
    for e in obs['elements']:
        if e['risk'] == 'human_auth' and e.get('tag') in ('input','textarea'):
            kind = human_kind(e)
            if kind:
                input_target = {'role':role_of(e),'name':nodes[e['ref']]}
                submit = None
                # Find the button related to this human challenge; leave all
                # other controls alone. The human-provided answer comes via core.
                for candidate in obs['elements']:
                    label = identify(candidate)
                    if role_of(candidate)=='button' and re.search(r'verify|continue|check|sign in|login',label,re.I):
                        submit = {'role':'button','name':nodes[candidate['ref']]}
                        break
                return {'kind':kind,'input':input_target,'submit':submit}
    return None


def receipt_from_observation(obs, info):
    # Never invent an application number. Require a portal-specific, reviewed
    # pattern AND the page to explicitly say this was successful.
    if not info.receipt_pattern or not re.search(r'successfully submitted|application (?:was )?received|submission successful',obs.get('text',''),re.I):
        return None
    match = re.search(info.receipt_pattern,obs.get('text',''))
    return match.group(1) if match and match.lastindex else None


def convert(obs, info):
    used, node_lookup, reverse = {}, {}, {}
    output = []
    for e in obs['elements']:
        role=role_of(e)
        label=identify(e)
        key=(role,label)
        used[key]=used.get(key,0)+1
        if used[key]>1: label=f'{label} [{used[key]}]'
        node_lookup[(role,label)] = e['ref']
        reverse[e['ref']]=label
        output.append({'ref':e['ref'],'role':role,'name':label,'value':e.get('value','') if not e.get('redacted') else '[redacted]'})
    info.nodes = node_lookup
    info.observation_id = obs['observation_id']
    info.auth_target = next((e['ref'] for e in obs['elements'] if e['risk']=='human_auth' and human_kind(e)),None)
    # Core should NEVER forward the unproven screenshot to WhatsApp.
    return {'url':obs['url'],'title':obs['title'],'nodes':output,'screenshot_base64':None,
            'screenshot_masked':False,'challenge':challenge_info(obs,reverse),
            'session_expired': bool(re.search(r'session expired|login again|timed out',obs.get('text',''),re.I)),
            'error': None,'receipt_number':receipt_from_observation(obs,info),
            'observation_id':obs['observation_id']}


@router.post('/session')
async def open_session(req:Open,x_internal_key:str|None=Header(None)):
    w=worker();w.require_key(x_internal_key)
    registry=settings()
    entry=registry.get(req.portal_id)
    if not isinstance(entry,dict) or not isinstance(entry.get('url'),str):
        raise HTTPException(422,'Unknown portal ID. Register an operator-reviewed portal URL in BROWSER_PORTALS_JSON')
    requested=entry['url']
    allowed={origin(u.strip()) for u in (os.getenv('BROWSER_ALLOWED_ORIGINS') or w.MOCK_URL).split(',') if u.strip()}
    if origin(requested) not in allowed:
        raise HTTPException(403,'Portal origin is not in BROWSER_ALLOWED_ORIGINS')
    async with w.creation_lock:
        from browser.general_routes import contexts
        if len(w.sessions)+len(contexts)>=int(os.getenv('MAX_BROWSER_SESSIONS','8')):
            raise HTTPException(429,'Browser capacity reached')
        context=await w.app.state.browser.new_context(viewport={'width':1180,'height':760},accept_downloads=False)
        page=await context.new_page()
        session=GeneralContext(context=context,page=page,allowed=allowed)
        await context.route('**/*',session.route)
        try:
            await page.goto(requested,wait_until='domcontentloaded',timeout=20000)
            await observe(session)
        except Exception:
            await context.close();raise
        contexts[session.id]=session
        sid=secrets.token_urlsafe(24)
        bridges[sid]=BridgeSession(context_id=session.id,portal_id=req.portal_id,
                       receipt_pattern=entry.get('receipt_pattern'))
        return {'session_id':sid}


@router.get('/session/{sid}/snapshot')
async def snapshot(sid:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        obs=await observe(ctx)
        response=convert(obs,info)
        info.fingerprint=ctx.fingerprint
        return response


@router.post('/session/{sid}/login')
async def login(sid:str,req:Login,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        obs=await observe(ctx)
        # Some services use passwordless/application-ID login; some have no ID.
        # Fill only a clearly identified user ID. Authentication verification
        # (OTP/CAPTCHA/face-auth) remains with the citizen.
        candidates=[e for e in obs['elements'] if e['tag']=='input' and e['risk']=='ordinary'
                    and re.search(r'login.?id|user.?id|registration.?id|application.?id|username|mobile number',identify(e),re.I)]
        if len(candidates)==1:
            e=candidates[0]
            await act(ctx,BrowserAction(action_id=str(uuid.uuid4()),observation_id=obs['observation_id'],
                     kind='fill',target_ref=e['ref'],value=req.portal_user_id,verified=True,source_ref='core:vault:portal_user_id'))
            obs=await observe(ctx)
        response=convert(obs,info)
        info.fingerprint=ctx.fingerprint
        return response


@router.post('/session/{sid}/authorize-submit')
async def authorize(sid:str,req:Authorization,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    if not req.approved:raise HTTPException(403,'Explicit citizen approval required')
    if req.review_observation_id != info.observation_id:
        raise HTTPException(409,'Review observation changed; a fresh citizen approval is required')
    if req.approval_ref in info.approval_refs:
        raise HTTPException(409,'Approval reference has already been used; new citizen review required')
    info.approval_refs.add(req.approval_ref)
    info.approval=(req.approval_ref,info.observation_id,time.time()+120)
    info.consumed=False
    return {'authorized':True,'expires_in':120}


@router.post('/session/{sid}/action')
async def action(sid:str,req:CoreAction,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        # Trust ONLY currently observed target names and the exact DOM state
        # presented to the planner. A page transition between snapshot and
        # action is a hard stop, not a reason to guess a selector.
        current_fingerprint,_,_,_,_=await signature(ctx)
        if info.fingerprint and current_fingerprint != info.fingerprint:
            raise HTTPException(409,'Page changed since the core snapshot; reobserve and replan')
        e_ref=info.nodes.get((req.target.role,req.target.name)) if req.target else None
        if req.target and not e_ref:raise HTTPException(409,'Target no longer observed; take a new snapshot')
        # Manual authentication is the ONLY credential-changing exception to
        # general autonomous actions; core has already obtained a human reply.
        observation=await observe(ctx)
        # Observe refreshes the UUID. Verify the previous page's control
        # fingerprint by checking actual exposed refs and labels, not UUID.
        e=next((x for x in observation['elements'] if x['ref']==e_ref),None)
        if req.target and (not e or (req.target.name.split(' [')[0] != identify(e))):
            raise HTTPException(409,'Target changed; re-plan using a new snapshot')
        kind={'click':'click','type':'fill','upload':'upload','wait':'wait','navigate':'navigate'}.get(req.type)
        if not kind:raise HTTPException(422,'Unsupported core action')
        if req.type=='type' and e and e['tag']=='select':kind='select'
        if req.type=='type' and e and e['risk']=='human_auth':
            if not human_kind(e):raise HTTPException(403,'Authentication step requires human control')
            # OTP/CAPTCHA provided via the trusted core's paused citizen reply.
            await ctx.targets[e_ref].fill(req.value or '')
            info.auth_value_entered=True
            after=await observe(ctx)
            convert(after,info)
            info.fingerprint=ctx.fingerprint
            return {'ok':True}
        if req.type=='click' and e and e['risk']!='ordinary':
            label=identify(e)
            if final_control(e):
                approval=info.approval
                if not approval or info.consumed or approval[2]<time.time():
                    raise HTTPException(403,'Submission requires an unexpired citizen approval from core')
                if info.observation_id!=approval[1]:raise HTTPException(409,'Review changed; reapprove before submitting')
                info.consumed=True  # fail closed on an uncertain submission
                # The operator must explicitly allow portal writes as well.
                if os.getenv('BROWSER_ENABLE_FINAL_SUBMIT','false').lower()!='true':
                    raise HTTPException(403,'Final submission is disabled by operator policy')
                await ctx.targets[e_ref].click(timeout=8000)
                after=await observe(ctx)
                convert(after,info)
                info.fingerprint=ctx.fingerprint
                return {'ok':True}
            if info.auth_value_entered and re.search(r'verify|continue|check|sign in|login',label,re.I):
                info.auth_value_entered=False
                await ctx.targets[e_ref].click(timeout=8000)
                after=await observe(ctx)
                convert(after,info)
                info.fingerprint=ctx.fingerprint
                return {'ok':True}
            raise HTTPException(403,'Irreversible browser action requires a dedicated human/approval workflow')
        if req.type=='upload':
            import base64
            try:raw=base64.b64decode(req.file_base64 or '',validate=True)
            except Exception:raise HTTPException(422,'Invalid uploaded document encoding')
            if len(raw)>1048576:raise HTTPException(413,'Prepared document exceeds current upload limit')
            mime=req.file_mime or 'application/pdf'
            if mime=='application/pdf' and not raw.startswith(b'%PDF-'):
                raise HTTPException(422,'Invalid PDF')
            if mime not in ('application/pdf','image/png','image/jpeg'):
                raise HTTPException(422,'Unsupported document MIME')
            upload={'name':req.file_name or 'document.pdf','mimeType':mime,'buffer':raw}
        else:upload=None
        command=BrowserAction(action_id=str(uuid.uuid4()),observation_id=observation['observation_id'],
                kind=kind,target_ref=e_ref,value=req.value or '',url=req.url or '',
                verified=req.type in ('type','upload'),source_ref='core:verified-profile' if req.type in ('type','upload') else None,
                timeout_ms=max(100,min(req.wait_ms or 5000,15000)))
        try:
            result=await act(ctx,command,upload)
        except HTTPException as exc:
            if exc.status_code in (403,409,422):raise
            return {'ok':False,'error':str(exc.detail)}
        info.observation_id=result['observation']['observation_id']
        # Update role/name mapping based on observed post-action page so next
        # core action can be grounded without waiting on a forced observation.
        convert(result['observation'],info)
        info.fingerprint=ctx.fingerprint
        return {'ok':True}


@router.delete('/session/{sid}')
async def close(sid:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info=bridges.pop(sid,None)
    if info:
        ctx=contexts.pop(info.context_id,None)
        if ctx:await ctx.context.close()
    return {'closed':True}

@router.get('/session/{sid}/view')
async def live_view(sid:str,x_internal_key:str|None=Header(None)):
    """Read-only operator preview. Raw screenshot is NEVER LLM/WhatsApp-safe."""
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        previous=(ctx.targets,ctx.observation_id,ctx.fingerprint,ctx.observed_at)
        try:
            obs=await observe(ctx)
            return {'url':obs['url'],'title':obs['title'],'screenshot_base64':obs['screenshot_base64'],
                    'screenshot_masked':False,'observed_at':obs['observed_at'],
                    'text':obs['text'][:4000], 'content_trust':'untrusted_website_data',
                    'warning':'Human-only browser screenshot. Never forward to model or messaging.'}
        finally:
            ctx.targets,ctx.observation_id,ctx.fingerprint,ctx.observed_at=previous
