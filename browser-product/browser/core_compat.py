"""Translate the existing next-wave LangGraph browser contract to live Playwright.

Lives on the PRIVATE worker at /core/session. The public browser API proxies this
under /core-browser/session with service authentication. This does not embed an
LLM: next-wave/app/planner.py makes every agent decision.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from playwright.async_api import TimeoutError as PWTimeout, Error as PWError
from pydantic import BaseModel, Field

from browser.general import GeneralContext, observe, act, origin, signature, intermediate_post_permitted, bound_tabs
from browser.step_policy import category, final_path
from browser.public_web import navigation_mode, NAV_MODE_PUBLIC, assert_public_url
from browser.general_routes import contexts
from browser.protocol import BrowserAction

router = APIRouter(prefix='/core')

# Legacy portal_id remains compatible. An updated core may provide a public
# HTTPS url and a consent reference when BROWSER_NAVIGATION_MODE=public-web.
class Open(BaseModel):
    portal_id: str | None = Field(default=None, min_length=1, max_length=80)
    url: str | None = Field(default=None, min_length=10, max_length=2000)
    consent_ref: str | None = Field(default=None, min_length=8, max_length=200)

class Login(BaseModel):
    portal_user_id: str = Field(min_length=1, max_length=200)

class Target(BaseModel):
    role: str
    name: str

class CoreAction(BaseModel):
    action_id: str | None = Field(default=None,min_length=8,max_length=100)
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
    auth_ref: str | None = None
    actions: dict = field(default_factory=dict)
    uncertain_action: str | None = None
    effect_started: bool = False
    last_action: str = ''
    receipt_pattern: str | None = None
    human_task_id: str | None = None
    human_expires: float = 0.0
    otp_sent: int = 0
    otp_window: float = 0.0
    otp_verify_count: int = 0

bridges: dict[str, BridgeSession] = {}
ACTION_HASH_KEY=secrets.token_bytes(32)


def worker():
    from browser import worker as w
    return w


def settings():
    try:
        entries = json.loads(os.getenv('BROWSER_PORTALS_JSON') or '{}')
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
    if e.get('type') == 'file' and e.get('tag') == 'input': return 'fileupload'
    if e['tag'] == 'a': return 'link'
    if e['tag'] == 'button' or e['type'] in ('button','submit','reset','image'): return 'button'
    if e['type'] in ('checkbox','radio'): return e['type']
    if e['tag'] == 'select': return 'combobox'
    if e['type'] in ('number','range'): return 'spinbutton'
    return 'textbox'


def identify(e):
    # Upload instructions must remain visible to the existing core planner,
    # which currently sees only role/name/value. Preserve these details in
    # the semantic name and also export structured metadata for newer clients.
    label = e.get('label') or e.get('name') or e.get('type') or e.get('ref')
    if e.get('type') == 'file' and e.get('tag') == 'input':
        attributes = ['file upload']
        if e.get('accept'):
            attributes.append('accepts: ' + str(e['accept'])[:180])
        if e.get('required'):
            attributes.append('required')
        if e.get('multiple'):
            attributes.append('multiple files')
        hint = str(e.get('description') or e.get('upload_hint') or '').strip()
        # Nearby page text is untrusted and potentially personal. It is a
        # helper hint, NOT a validated portal specification.
        hint = re.sub(r'\b\d[\d -]{10,}\d\b', '[redacted identifier]', hint)[:160]
        if hint and hint not in label:
            attributes.append('page hint: ' + hint)
        return str(label)[:180] + ' (' + '; '.join(attributes) + ')'
    return label


def human_kind(e):
    label = ' '.join(str(e.get(k, '')) for k in ('label','name','autocomplete','type'))
    if e.get('auth_kind')=='otp':return 'otp'
    if re.search(r'captcha|security.?code|human.?verification',label,re.I): return 'captcha'
    if re.search(r'otp|one.time|verification.?code|auth.?code',label,re.I): return 'otp'
    return None


def final_control(e):
    return e.get('category') in ('final','final_unknown')


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
        output.append({'ref':e['ref'],'role':role,'name':label,
                       'value':e.get('value','') if not e.get('redacted') else '[redacted]',
                       # Additive metadata: legacy PageNode ignores extras;
                       # updated core can use them for rigorous upload checks.
                       'element_type':e.get('type',''),
                       'action_category':e.get('category','ordinary'),
                       'form_method':e.get('form_method',''),
                       'form_action':e.get('form_action',''),
                       'dedicated_upload_form':bool(e.get('form_upload_only',False)),
                       'accept':e.get('accept','') if role=='fileupload' else '',
                       'required':bool(e.get('required',False)),
                       'multiple':bool(e.get('multiple',False)),
                       'description':e.get('description','') if role=='fileupload' else '',
                       'upload_hint':e.get('upload_hint','') if role=='fileupload' else ''})
    info.nodes = node_lookup
    info.observation_id = obs['observation_id']
    info.auth_target = next((e['ref'] for e in obs['elements'] if e['risk']=='human_auth' and human_kind(e)),None)
    # Core should NEVER forward the unproven screenshot to WhatsApp.
    return {'url':obs['url'],'title':obs['title'],'nodes':output,
            'page_text':obs.get('text','')[:3500],
            'observation_truncated':bool(obs.get('truncated',False)),
            'screenshot_base64':None,
            'screenshot_masked':False,'challenge':challenge_info(obs,reverse),
            'session_expired': bool(re.search(r'session expired|login again|timed out',obs.get('text',''),re.I)),
            'error': None,'receipt_number':receipt_from_observation(obs,info),
            'observation_id':obs['observation_id']}


@router.post('/session')
async def open_session(req:Open,x_internal_key:str|None=Header(None)):
    w=worker();w.require_key(x_internal_key)
    dynamic = navigation_mode() == NAV_MODE_PUBLIC
    registry=settings()
    entry = None
    if req.url:
        if not dynamic:
            raise HTTPException(403,'Dynamic URLs are disabled; enable public-web mode explicitly')
        if not req.consent_ref:
            raise HTTPException(422,'Citizen browsing consent reference is required for a dynamic URL')
        if req.portal_id and req.portal_id in registry:
            raise HTTPException(422,'Choose either a registered portal ID or a dynamic URL')
        requested = req.url
        await assert_public_url(requested)
    else:
        if not req.portal_id:
            raise HTTPException(422,'Provide a portal_id or a consent-backed URL')
        entry = registry.get(req.portal_id)
        if not isinstance(entry,dict) or not isinstance(entry.get('url'),str):
            raise HTTPException(422,'Unknown portal ID; provide a dynamic URL with consent or configure the portal registry')
        requested = entry['url']
        if dynamic:
            await assert_public_url(requested)
    allowed={origin(u.strip()) for u in (os.getenv('BROWSER_ALLOWED_ORIGINS') or w.MOCK_URL).split(',') if u.strip()} if not dynamic else set()
    if not dynamic and origin(requested) not in allowed:
        raise HTTPException(403,'Portal origin is not in BROWSER_ALLOWED_ORIGINS')
    async with w.creation_lock:
        from browser.general_routes import contexts
        if len(w.sessions)+len(contexts)>=int(os.getenv('MAX_BROWSER_SESSIONS','8')):
            raise HTTPException(429,'Browser capacity reached')
        context=None
        try:
            context=await w.app.state.browser.new_context(viewport={'width':1180,'height':760},accept_downloads=False,service_workers='block')
            page=await context.new_page()
            session=GeneralContext(context=context,page=page,allowed=allowed,public_web=dynamic)
            bound_tabs(session)
            await context.route('**/*',session.route)
            await context.route_web_socket('**/*',lambda socket:socket.close())
            await page.goto(requested,wait_until='domcontentloaded',timeout=20000)
            await observe(session)
        except BaseException as exc:
            failure_ref=uuid.uuid4().hex[:12]
            reason='unexpected_browser_failure';status=502
            if isinstance(exc,PWTimeout):reason='navigation_timeout';status=504
            elif isinstance(exc,PWError):
                for token,category in [('ERR_BLOCKED_BY_ADMINISTRATOR','environment_blocked_by_admin'),('ERR_NAME_NOT_RESOLVED','dns_failure'),('ERR_CERT','tls_failure'),('ERR_CONNECTION','connection_failure')]:
                    if token in str(exc):reason=category;break
            if context is not None:
                try:await context.close()
                except Exception:pass
            import logging
            logging.getLogger(__name__).warning('browser_open_failed ref=%s reason=%s active_contexts=%d',failure_ref,reason,len(contexts))
            if not isinstance(exc,Exception) or isinstance(exc,HTTPException):raise
            raise HTTPException(status,f'Browser open failed: {reason}; reference={failure_ref}. Run worker navigation diagnostics.') from None
        contexts[session.id]=session
        sid=secrets.token_urlsafe(24)
        bridges[sid]=BridgeSession(context_id=session.id,portal_id=req.portal_id or 'dynamic-public-web',
                       receipt_pattern=entry.get('receipt_pattern') if entry else None)
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
    async with ctx.lock:
        if contexts.get(info.context_id) is not ctx:raise HTTPException(404,'Browser context closed')
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
    if worker().MODE=='integrated' and not req.action_id:
        raise HTTPException(422,'action_id is required in integrated mode; retain it when retrying the same request')
    async with ctx.lock:
        if contexts.get(info.context_id) is not ctx:raise HTTPException(404,'Browser context was closed')
        if info.uncertain_action:raise HTTPException(409,'Previous core action outcome unknown; inspect and reconcile before reopening a session')
        info.effect_started=False
        fingerprint=hmac.new(ACTION_HASH_KEY,req.model_dump_json().encode(),hashlib.sha256).hexdigest()
        if req.action_id:
            prior=info.actions.get(req.action_id)
            if prior:
                if prior['fingerprint']!=fingerprint:raise HTTPException(409,'Action ID reused with different input')
                if prior['result'] is None:raise HTTPException(409,'Action outcome unknown; reconcile before issuing another action')
                return {**prior['result'],'replayed':True}
            if len(info.actions)>=1000:raise HTTPException(429,'Session action ledger full; close and reconcile the session')
            info.actions[req.action_id]={'fingerprint':fingerprint,'result':None}
        try:
            result=await action_locked(sid,req,info,ctx)
        except HTTPException as exc:
            if info.effect_started:info.uncertain_action=req.action_id or 'legacy-action'
            # Only clearly pre-action staleness is safe to plan afresh.
            if req.action_id and not info.effect_started:
                info.actions.pop(req.action_id,None)
            raise
        except BaseException:
            if info.effect_started:info.uncertain_action=req.action_id or 'legacy-action'
            raise
        if req.action_id:info.actions[req.action_id]['result']=result
        return result

async def action_locked(sid,req,info,ctx):
    expire_human(info,ctx)
    if info.human_task_id:
        raise HTTPException(409,'Human assistance owns this browser session; wait for completion')
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
    if req.target and (not e or (req.target.name != identify(e) and not (req.target.name.startswith(str(identify(e))+' [') and re.fullmatch(r' \[\d+\]',req.target.name[len(str(identify(e))):])))):
        raise HTTPException(409,'Target changed; re-plan using a new snapshot')
    kind={'click':'click','type':'fill','upload':'upload','wait':'wait','navigate':'navigate'}.get(req.type)
    if not kind:raise HTTPException(422,'Unsupported core action')
    if req.type=='type' and e and e['tag']=='select':kind='select'
    if req.type=='type' and e and e['risk']=='human_auth':
        if not human_kind(e):raise HTTPException(403,'Authentication step requires human control')
        # OTP/CAPTCHA provided via the trusted core's paused citizen reply.
        info.effect_started=True
        await ctx.targets[e_ref].fill(req.value or '')
        info.auth_value_entered=True;info.auth_ref=e_ref
        after=await observe(ctx)
        convert(after,info)
        info.fingerprint=ctx.fingerprint
        return {'ok':True}
    if req.type=='click' and e and e['risk']!='ordinary':
        label=identify(e)
        intent=e.get('category','ordinary')
        if final_control(e):
            approval=info.approval
            if not approval or info.consumed or approval[2]<time.time():
                raise HTTPException(403,'Submission requires unexpired citizen approval from core')
            if info.observation_id!=approval[1]:raise HTTPException(409,'Review changed; reapprove before submitting')
            if os.getenv('BROWSER_ENABLE_FINAL_SUBMIT','false').lower()!='true':
                raise HTTPException(403,'Final submission is disabled by operator policy')
            # A generic form is NOT a validated application adapter. Its
            # network write may still be blocked by route() on public-web.
            info.consumed=True
            info.effect_started=True
            await ctx.targets[e_ref].click(timeout=8000)
            after=await observe(ctx);convert(after,info);info.fingerprint=ctx.fingerprint
            return {'ok':True}
        if intent == 'otp_send':
            # No model-driven repeat flood. Core holds a consent-backed
            # session, but further requests require new user supervision.
            now=time.time()
            if now-info.otp_window>600:info.otp_window=now;info.otp_sent=0
            if info.otp_sent>=2:raise HTTPException(429,'OTP request limit reached; pause for human assistance')
            if not re.search(r'otp|login|verification|sign in|sign-in',observation.get('text',''),re.I):
                raise HTTPException(403,'OTP request not supported by current page context')
            info.otp_sent+=1
            info.effect_started=True
            await scoped_interaction(ctx,ctx.targets[e_ref],intent)
            after=await observe(ctx);convert(after,info);info.fingerprint=ctx.fingerprint
            return {'ok':True,'kind':'otp_request','requires_human_otp':True}
        if intent=='otp_verify' and info.auth_value_entered:
            auth=next((c for c in observation['elements'] if c['ref']==info.auth_ref),None)
            if not auth or (auth.get('frame_id'),auth.get('form_index'))!=(e.get('frame_id'),e.get('form_index')):raise HTTPException(403,'Verification value belongs to a different form')
            verify_attempt(info)
            info.auth_value_entered=False;info.auth_ref=None
            info.effect_started=True
            await scoped_interaction(ctx,ctx.targets[e_ref],intent)
            after=await observe(ctx);convert(after,info);info.fingerprint=ctx.fingerprint
            return {'ok':True,'kind':'auth_verification','verified':False}
        if intent=='upload_step':
            # Verify the file belongs to THIS form. Attaching a file to
            # an unrelated input must never unlock a Submit button.
            attached=any(c.get('type')=='file' and c.get('file_count',0)>0
                         and c.get('form_index',-1)==e.get('form_index')
                         and c.get('frame_id')==e.get('frame_id')
                         for c in observation['elements'])
            if not attached:
                raise HTTPException(409,'Attach a document to this upload form before clicking Upload')
            if e.get('form_upload_only'):
                # Only a dedicated file-only POST with a positive upload
                # endpoint can run without an operator-review wildcard.
                # The request interceptor permits that exact POST URL for
                # this click and still blocks final/application paths.
                info.effect_started=True
                await scoped_interaction(ctx,ctx.targets[e_ref],'upload_form',post_target=e['form_action'])
            else:
                if not intermediate_post_permitted(ctx.page.url,public_web=ctx.public_web):
                    raise HTTPException(403,'Upload action requires an operator-reviewed intermediate POST origin or human assistance')
                info.effect_started=True
                await ctx.targets[e_ref].click(timeout=8000)
            after=await observe(ctx);convert(after,info);info.fingerprint=ctx.fingerprint
            return {'ok':True,'kind':'document_upload_step','confirmed_by_portal':False}
        raise HTTPException(403,'Sensitive action requires human assistance or a reviewed portal adapter')
    if req.type=='upload':
        if not e or e.get('type')!='file':
            raise HTTPException(422,'Upload action requires an observed file input; use the fileupload role')
        import base64
        try:raw=base64.b64decode(req.file_base64 or '',validate=True)
        except Exception:raise HTTPException(422,'Invalid uploaded document encoding')
        from browser.document_validation import validate_document
        mime=req.file_mime or 'application/pdf'
        filename=req.file_name or 'document.pdf'
        validate_document(raw,filename,mime)
        upload={'name':filename,'mimeType':mime,'buffer':raw}
    else:upload=None
    command=BrowserAction(action_id=str(uuid.uuid4()),observation_id=observation['observation_id'],
            kind=kind,target_ref=e_ref,value=req.value or '',url=req.url or '',
            verified=req.type in ('type','upload'),source_ref='core:verified-profile' if req.type in ('type','upload') else None,
            timeout_ms=max(100,min(req.wait_ms or 5000,15000)))
    try:
        try:result=await act(ctx,command,upload)
        finally:info.effect_started=ctx.last_effect_started
    except HTTPException as exc:
        if exc.status_code in (403,409,422):raise
        return {'ok':False,'error':str(exc.detail)}
    info.observation_id=result['observation']['observation_id']
    # Update role/name mapping based on observed post-action page so next
    # core action can be grounded without waiting on a forced observation.
    convert(result['observation'],info)
    info.fingerprint=ctx.fingerprint
    return {'ok':True}

async def scoped_interaction(ctx,locator,intent,post_target=None):
    """Permit a vetted write during this single observed click only.

    Auth challenges are same-origin scoped. A dedicated upload form instead
    binds to the exact observed POST URL (never an arbitrary same-origin POST).
    Final-submission network paths are denied in either case.
    """
    try:
        scope_origin=origin(ctx.page.url)
        if intent=='upload_form':
            if not post_target or origin(post_target)!=scope_origin or final_path(post_target):
                raise HTTPException(403,'Upload target needs a reviewed portal adapter')
            ctx.write_scope=(scope_origin,intent,post_target.split('#',1)[0].split('?',1)[0])
            ctx.write_event=asyncio.Event()
        else:ctx.write_scope=(scope_origin,intent)
    except ValueError:ctx.write_scope=None  # in-memory about:blank test fixture only
    try:
        await locator.click(timeout=8000)
        if intent=='upload_form' and ctx.write_event:
            try:await asyncio.wait_for(ctx.write_event.wait(),1)
            except asyncio.TimeoutError:pass
    finally:
        ctx.write_scope=None;ctx.write_event=None


async def challenge_regions(ctx):
    """Only human-auth challenge surfaces, never arbitrary screenshot clicks."""
    boxes=[]
    for frame in ctx.page.frames[1:]:
        try:
            element=await frame.frame_element()
            identity=await element.evaluate("e=>[e.id,e.title,e.name,e.getAttribute('aria-label'),e.getAttribute('src')].join(' ')")
            if not re.search(r'captcha|recaptcha|hcaptcha|turnstile',frame.url+' '+identity,re.I):continue
            region=await element.bounding_box()
            if region: boxes.append(region)
        except Exception:pass
    # Sites often serve CAPTCHA pixels from blob/data URLs; use DOM identity,
    # accessible labels and associated verification fields, not URL alone.
    for frame in ctx.page.frames:
        if frame != ctx.page.main_frame and not ctx.permitted(frame.url):
            continue
        locator=frame.locator('img,canvas,[role=img]')
        for i in range(min(await locator.count(),100)):
            image=locator.nth(i)
            try:
                marked=await image.evaluate(r"""e=>{
                  const own=[e.id,e.className,e.getAttribute('alt'),e.getAttribute('title'),e.getAttribute('aria-label'),e.getAttribute('src')].join(' ');
                  if(/captcha|human[ _-]?verification|security[ _-]?(?:image|challenge)/i.test(own))return true;
                  const group=e.closest('label,fieldset,[role=group]')||e.parentElement;
                  return !!group && /captcha|human verification/i.test(group.innerText||'') && !!group.querySelector('input');
                }""")
                region=await image.bounding_box() if marked and await image.is_visible() else None
                if region and region['width']>0 and region['height']>0:boxes.append(region)
            except Exception:pass
    return boxes


class HumanBegin(BaseModel):
    task_id: str = Field(min_length=8,max_length=100)
    expires_at: float | None = None

class HumanAction(BaseModel):
    observation_id: str | None = None
    task_id: str = Field(min_length=8,max_length=100)
    kind: str
    target_ref: str | None = None
    value: str = Field(default='',max_length=100)
    x: float | None = None
    y: float | None = None


def release_human(info,ctx):
    info.human_task_id=None;info.human_expires=0.0;ctx.human_captcha_until=0.0
    info.auth_value_entered=False;info.auth_ref=None

def expire_human(info,ctx):
    if info.human_task_id and info.human_expires<=time.time():release_human(info,ctx)

def verify_attempt(info):
    if info.otp_verify_count>=5:raise HTTPException(429,'Too many verification attempts; stop and check the official portal')
    info.otp_verify_count+=1

def ensure_human(info, task_id):
    if info.context_id not in contexts:raise HTTPException(404,'Browser context closed')
    if not info.human_task_id or info.human_expires<=time.time() or not secrets.compare_digest(info.human_task_id,task_id):
        raise HTTPException(403,'No active human assistance task for this session')


@router.get('/session/{sid}/human-status')
async def human_status(sid:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        expire_human(info,ctx)
        return {'state':'active' if info.human_task_id else 'none','task_id':info.human_task_id,
                'expires_at':info.human_expires,'needs_reconciliation':bool(info.uncertain_action)}

@router.post('/session/{sid}/human-begin')
async def human_begin(sid:str,req:HumanBegin,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        if contexts.get(info.context_id) is not ctx:raise HTTPException(404,'Browser context closed')
        expire_human(info,ctx)
        if info.human_task_id:raise HTTPException(409,'Session already assigned to a human')
        if req.expires_at and not time.time()<req.expires_at<=time.time()+601:raise HTTPException(422,'Human task expiry must be within 600 seconds')
        info.human_task_id=req.task_id
        info.human_expires=req.expires_at or (time.time()+300)
        ctx.human_captcha_until=info.human_expires
    return {'state':'paused_for_human'}


@router.post('/session/{sid}/human-view')
async def human_view(sid:str,req:HumanBegin,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid);ensure_human(info,req.task_id)
    async with ctx.lock:
        ensure_human(info,req.task_id)
        obs=await observe(ctx)
        # Filter to controls useful for manual verification only. No raw OTP
        # values are returned and no screenshot is sent to the LLM.
        controls=[{'ref':e['ref'],'label':e['label'],'category':e['category'],
                   'type':e['type'],'bounds':e['bounds']} for e in obs['elements']
                  if e['category'] in ('human_input','otp_send','otp_verify','upload_step','captcha_refresh')]
        captcha_boxes=await challenge_regions(ctx)
        return {'state':'human_in_control','url':obs['url'],'screenshot_base64':obs['screenshot_base64'],
                'viewport':obs['viewport'],'controls':controls,'challenge_boxes':captcha_boxes,
                'human_signals':obs['human_signals'],'observation_id':obs['observation_id']}


@router.post('/session/{sid}/human-act')
async def human_act(sid:str,req:HumanAction,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid);ensure_human(info,req.task_id)
    async with ctx.lock:
        ensure_human(info,req.task_id)
        if req.observation_id:
            fingerprint,*_=await signature(ctx)
            if req.observation_id!=ctx.observation_id or fingerprint!=ctx.fingerprint:
                raise HTTPException(409,'Verification page changed; refresh before interacting')
        obs=await observe(ctx)
        e=next((c for c in obs['elements'] if c['ref']==req.target_ref),None)
        if req.kind=='fill':
            if not e or e['category']!='human_input' or e['tag'] not in ('input','textarea'):
                raise HTTPException(403,'Only observed verification fields can be filled by this link')
            # Do not log, persist, echo or store the supplied OTP/CAPTCHA text.
            await ctx.targets[e['ref']].fill(req.value,timeout=8000)
            info.auth_value_entered=True
        elif req.kind=='click':
            if not e or e['category'] not in ('otp_send','otp_verify','upload_step','captcha_refresh'):
                raise HTTPException(403,'Human link cannot click final/unknown controls')
            if e['category']=='upload_step' and not any(c.get('type')=='file' and c.get('file_count')
                and c.get('form_index',-1)==e.get('form_index') and c.get('frame_id')==e.get('frame_id') for c in obs['elements']):
                raise HTTPException(409,'Attach the document to this upload form before using the upload button')
            if e['category']=='otp_send':
                now=time.time()
                if now-info.otp_window>600:info.otp_window=now;info.otp_sent=0
                if info.otp_sent>=2:raise HTTPException(429,'OTP resend limit reached; wait or request official support')
                info.otp_sent+=1
            if e['category']=='otp_verify':
                verify_attempt(info)
            if e['category']=='upload_step' and e.get('form_upload_only'):
                await scoped_interaction(ctx,ctx.targets[e['ref']], 'upload_form',post_target=e['form_action'])
            else:
                await scoped_interaction(ctx,ctx.targets[e['ref']], 'human_challenge')
        elif req.kind=='challenge_click':
            if req.x is None or req.y is None:raise HTTPException(422,'Click coordinates are required')
            matched=any(r['x']<=req.x<=r['x']+r['width'] and r['y']<=req.y<=r['y']+r['height'] for r in await challenge_regions(ctx))
            if not matched:raise HTTPException(403,'Coordinate click is restricted to observed CAPTCHA images or challenge frames')
            await ctx.page.mouse.click(req.x,req.y)
        else:raise HTTPException(422,'Unsupported human control')
        after=await observe(ctx)
        convert(after,info);info.fingerprint=ctx.fingerprint
        return {'ok':True,'page_changed':True}


@router.post('/session/{sid}/human-finish')
async def human_finish(sid:str,req:HumanBegin,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid);ensure_human(info,req.task_id)
    async with ctx.lock:
        ensure_human(info,req.task_id)
        obs=await observe(ctx)
        # A citizen attestation is not proof that the challenge was solved;
        # core receives an explicit unverified flag and MUST re-inspect.
        release_human(info,ctx)
        convert(obs,info);info.fingerprint=ctx.fingerprint
        return {'state':'resumed','verified':False,'still_waiting_human':bool(obs['human_signals']),
                'observation_id':obs['observation_id']}


@router.post('/session/{sid}/human-cancel')
async def human_cancel(sid:str,req:HumanBegin,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info,ctx=get(sid)
    async with ctx.lock:
        ensure_human(info,req.task_id)
        release_human(info,ctx)
    return {'state':'cancelled'}


@router.delete('/session/{sid}')
async def close(sid:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key)
    info=bridges.get(sid)
    if info:
        ctx=contexts.get(info.context_id)
        if ctx:
            async with ctx.lock:
                release_human(info,ctx)
                bridges.pop(sid,None);contexts.pop(info.context_id,None)
                await ctx.context.close()
        else:bridges.pop(sid,None)
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
