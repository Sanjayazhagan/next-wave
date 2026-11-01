"""General observed-page execution, independent of the fictional portal adapter.

Core supplies model decisions. This module never calls an AI, solves a challenge,
infers applicant data or permits generic final form submission.
"""
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
import base64
from dataclasses import dataclass,field
import hashlib
import hmac
import secrets
import json
import re
import time
import uuid
from urllib.parse import urlsplit,urlunsplit
from fastapi import HTTPException
from playwright.async_api import Error as BrowserError
from browser.protocol import BrowserAction
from browser.public_web import assert_public_url, public_url_syntax
from browser.step_policy import category, final_path, OTP_VERIFY

# Human-only CAPTCHA providers; no agent-side solver or challenge bypass.
CAPTCHA_PROVIDER_SUFFIXES=('recaptcha.net','google.com','hcaptcha.com','challenges.cloudflare.com','turnstile.cloudflare.com')

def trusted_captcha_provider(url):
    p=urlsplit(url)
    host=(p.hostname or '').lower()
    return p.scheme=='https' and any(host==suffix or host.endswith('.'+suffix) for suffix in CAPTCHA_PROVIDER_SUFFIXES) and bool(re.search(r'captcha|recaptcha|hcaptcha|turnstile|challenge', p.path, re.I))


CONTROLS='a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[role=checkbox],[role=radio],[role=combobox],[role=option],[role=tab],[role=menuitem],[role=gridcell],[contenteditable=true]'
AUTH=re.compile(r'password|one.?time|\botp\b|captcha|verification code|security code|face.?auth',re.I)
IDENTIFIER=re.compile(r'aadhaar|aadhar|bank|account.?number|card.?number|passport|national.?id|cc-number',re.I)
IRREVERSIBLE=re.compile(r'logout|log.?out|sign.?out|account/close|api/transfer|submit|finali[sz]e|confirm.?application|pay\b|purchase|delete|remove.?account|approve.?application|apply.?now|register.?account',re.I)


def origin(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('Only configured HTTP(S) origins without URL credentials are accepted')
    return f'{p.scheme}://{p.hostname.lower()}:{p.port or (443 if p.scheme=="https" else 80)}'


def safe_url(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))



def intermediate_post_permitted(url:str,*,public_web:bool)->bool:
    """POST allowed only on operator-reviewed exact origins in public-web mode.

    Historical BROWSER_ALLOW_FORM_POST is retained for fixed-origin
    development only. Never enable it as a wildcard for arbitrary websites.
    This policy does not authorize final submission and can't classify an
    arbitrary POST as merely intermediate; deployments must audit each site.
    """
    import os
    try:
        dest=origin(url)
        reviewed={origin(u.strip()) for u in os.getenv('BROWSER_INTERMEDIATE_POST_ORIGINS','').split(',') if u.strip()}
        if dest in reviewed:
            return True
        return not public_web and os.getenv('BROWSER_ALLOW_FORM_POST','false').lower()=='true'
    except ValueError:
        return False

@dataclass
class GeneralContext:
    context:object
    page:object
    allowed:set[str]
    public_web:bool=False
    id:str=field(default_factory=lambda:str(uuid.uuid4()))
    generation:str=field(default_factory=lambda:str(uuid.uuid4()))
    lock:asyncio.Lock=field(default_factory=asyncio.Lock)
    targets:dict=field(default_factory=dict)
    observation_id:str=''
    fingerprint:str=''
    observed_at:float=0
    last_used:float=field(default_factory=time.time)
    tab_ids:dict=field(default_factory=dict)
    action_results:dict=field(default_factory=dict)
    dialogs:list=field(default_factory=list)
    download_events:int=0
    last_effect_started:bool=False
    private_values:set=field(default_factory=set)
    last_elements:dict=field(default_factory=dict)
    last_visible_text:str=''
    link_offset:int=0
    link_query:str=''
    last_navigation_status:int|None=None
    observed_url:str=''
    navigation_statuses:dict=field(default_factory=dict)
    native_submit_scope:tuple|None=None
    native_submit_event:object=None
    write_event:object=None
    write_scope:tuple|None=None  # (origin, intent, optional exact URL); only during a vetted click
    human_captcha_until:float=0.0

    def permitted(self,url):
        if self.public_web:
            try:
                public_url_syntax(url)
                return True
            except ValueError:
                return False
        try:return origin(url) in self.allowed
        except ValueError:return False

    async def check_destination(self,url):
        if not self.permitted(url):
            raise HTTPException(403,'Navigation destination is not permitted')
        if self.public_web:
            await assert_public_url(url)

    async def route(self,route):
        # Ordinary reading works across public HTTPS destinations. Writes do
        # NOT: intermediate form POSTs require an exact operator-reviewed
        # origin, even in public-web mode. This is not a final-submit bypass.
        method = route.request.method.upper()
        url = route.request.url
        if not self.permitted(url):
            return await route.abort('blockedbyclient')
        native_scoped=bool(self.native_submit_scope and (method,origin(url),urlsplit(url).path or '/')==self.native_submit_scope)
        if method not in ('GET','HEAD','OPTIONS'):
            scoped = (self.write_scope is not None and method == 'POST'
                      and origin(url) == self.write_scope[0]
                      and (self.write_scope[1] in ('otp_send','otp_verify','human_challenge')
                           or (self.write_scope[1] == 'upload_form'
                               and len(self.write_scope) == 3
                               and safe_url(url) == self.write_scope[2])))
            # Provider POSTs needed for manual CAPTCHA completion. Enabled
            # only during a scoped live human task and only to known HTTPS
            # challenge endpoints; never generic agent or site POST permission.
            captcha_scoped = method=='POST' and time.time()<self.human_captcha_until and trusted_captcha_provider(url)
            if not (scoped or captcha_scoped or native_scoped) and (method != 'POST' or not intermediate_post_permitted(url,public_web=self.public_web)):
                return await route.abort('blockedbyclient')
        # A path that suggests final submission remains forbidden as a generic
        # request, including from scripts. A real integration must use a
        # separately audited, site-specific approval adapter for these URLs.
        if not native_scoped and (final_path(url) or IRREVERSIBLE.search(urlsplit(url).path+' '+urlsplit(url).query)):
            return await route.abort('blockedbyclient')
        if native_scoped:
            self.native_submit_scope=None
            if self.native_submit_event:self.native_submit_event.set()
        if method=='POST' and scoped and self.write_scope and self.write_scope[1]=='upload_form':
            self.write_scope=None
            if self.write_event:self.write_event.set()
        if self.public_web:
            try:
                await assert_public_url(url)
            except HTTPException:
                return await route.abort('blockedbyclient')
        return await route.continue_()

    def tab_id(self,page):
        if page not in self.tab_ids:self.tab_ids[page]=str(uuid.uuid4())
        return self.tab_ids[page]


@asynccontextmanager
async def lock_guard(lock,timeout=5,status=409):
    try:await asyncio.wait_for(lock.acquire(),timeout)
    except asyncio.TimeoutError:raise HTTPException(status,'Another browser operation is in progress; retry after it completes',headers={'X-Browser-Outcome':'not_applied','Retry-After':'1'}) from None
    try:yield
    finally:lock.release()


def watch_navigation(session):
    def response_seen(response):
        try:
            if response.request.is_navigation_request() and response.frame.parent_frame is None:
                session.navigation_statuses[response.frame.page]=response.status
        except BrowserError:pass
    session.context.on('response',response_seen)


def bound_tabs(session):
    import os
    try:limit=int(os.getenv('MAX_BROWSER_TABS','8'))
    except ValueError:raise HTTPException(503,'Invalid browser tab limit')
    if not 1<=limit<=32:raise HTTPException(503,'Browser tab limit must be between 1 and 32')
    def download_seen(download):session.download_events+=1
    async def opened(page):
        page.on('download',download_seen)
        if len(session.context.pages)>limit:
            await page.close()
            session.dialogs.append({'kind':'tab_limit','disposition':'closed','message_retained':False})
            session.dialogs=session.dialogs[-20:]
    session.context.on('page',opened)
    for page in session.context.pages:page.on('download',download_seen)


FORM_HASH_KEY=secrets.token_bytes(32)
CENSUS_BATCH=Path(__file__).with_name('dom_census.js').read_text(encoding='utf-8')

async def census(session):
    """Bounded DOM/accessible controls, including permitted frames and open shadow roots."""
    elements=[];targets={};frames=[];truncated=False
    deadline=asyncio.get_running_loop().time()+8
    session.inspection_incomplete=False
    for frame_index,frame in enumerate(session.page.frames[:12]):
        if asyncio.get_running_loop().time()>=deadline:
            truncated=True;session.inspection_incomplete=True;break
        frame_id=f'frame-{frame_index}'
        allowed=session.permitted(frame.url) or (frame.url in ('about:blank','about:srcdoc') and frame==session.page.main_frame)
        frames.append({'id':frame_id,'url':safe_url(frame.url),'available':allowed})
        if not allowed:continue
        # Scan form controls first: long government-portal navigation menus
        # otherwise exhaust the 250-element budget before reaching any inputs.
        priority=frame.locator('input:not([type=hidden]),select,textarea,button,[role=button],[role=checkbox],[role=radio],[role=combobox],[role=option],[role=tab],[role=menuitem],[role=gridcell],[contenteditable=true]')
        links=frame.locator('a[href],[role=link]')
        configs=[{'offset':0,'query':'','limit':250-len(elements)},
                 {'offset':session.link_offset,'query':session.link_query.lower(),'limit':min(160,250-len(elements))}]
        try:primary_count=await asyncio.wait_for(priority.count(),min(2,max(.05,deadline-asyncio.get_running_loop().time())))
        except (asyncio.TimeoutError,BrowserError):
            frames[-1]['available']=False;frames[-1]['reason']='inspection_timeout';truncated=True
            if frame_index==0:session.inspection_incomplete=True
            continue
        for group_index,group in enumerate((priority,links)):
            config=configs[group_index];config['limit']=min(config['limit'],250-len(elements))
            try:batch=await asyncio.wait_for(group.evaluate_all(CENSUS_BATCH,config),min(2.5,max(.05,deadline-asyncio.get_running_loop().time())))
            except (asyncio.TimeoutError,BrowserError):
                truncated=True
                if frame_index==0:session.inspection_incomplete=True
                continue
            truncated=truncated or batch['truncated']
            for item in batch['results']:
                offset=item['index'];index=offset if group_index==0 else primary_count+offset
                loc=group.nth(offset);data=item['data']
                hidden=data.pop('_hidden_fields',[])
                files=data.pop('_files',[])
                data['file_state_digest']=hmac.new(FORM_HASH_KEY,json.dumps(files,sort_keys=True).encode(),hashlib.sha256).hexdigest()
                data['form_state_digest']=hmac.new(FORM_HASH_KEY,json.dumps(hidden,sort_keys=True).encode(),hashlib.sha256).hexdigest()
                data['label']=data['label'].strip()[:300];data['name']=data['name'][:100]
                data['upload_hint']=data.get('upload_hint','').strip()[:320]
                data['destination_state_digest']=hmac.new(FORM_HASH_KEY,json.dumps([data['href'],data['form_action']]).encode(),hashlib.sha256).hexdigest()
                if data['form_action']:data['form_action']=safe_url(data['form_action'])
                description=' '.join((data['label'],data['name'],data['type'],data['autocomplete']))
                sensitive=bool(AUTH.search(description));private=bool(IDENTIFIER.search(description))
                data.update(category='ordinary',risk='ordinary',redacted=sensitive or private)
                ref=f"{frame_id}-node-{data['node_identity']}"
                data.update(ref=ref,frame_id=frame_id,frame_url=safe_url(frame.url))
                # Child frames need Playwright's viewport coordinate conversion.
                try:box=item['box'] if frame==session.page.main_frame else await asyncio.wait_for(loc.bounding_box(),2)
                except (BrowserError,asyncio.TimeoutError):
                    truncated=True;continue
                viewport=session.page.viewport_size or {'width':1180,'height':760}
                if frame!=session.page.main_frame and box is None and data['type']!='file':continue
                data['bounds']=box
                data['in_viewport']=bool(box and box['x']+box['width']>0 and box['y']+box['height']>0 and box['x']<viewport['width'] and box['y']<viewport['height'])
                data['value']='[redacted]' if data['redacted'] else str(data['value'])[:500]
                if data['href']:
                    from urllib.parse import urljoin
                    data['href']=safe_url(urljoin(frame.url,data['href']))
                targets[ref]=loc;elements.append(data)
        if len(elements)>=250:truncated=True;break
    # Form context is known only after gathering all controls, including
    # hidden upload inputs. Reclassify the entire observation consistently.
    has_file=any(e['type']=='file' for e in elements)
    has_auth=any(e['redacted'] and e['tag'] in ('input','textarea') and AUTH.search(e['label']+' '+e['type']) for e in elements)
    has_verify_button=any(OTP_VERIFY.search(e['label']) and e['tag'] in ('button','input') for e in elements)
    for e in elements:
        kind=category(e,has_file=has_file,has_auth=has_auth)
        # Numeric OTP widgets commonly expose accessibility role=spinbutton
        # and a label like 'Code' rather than 'OTP'. Only treat one as a
        # human-only OTP field if a *separate* Verify OTP control is observed.
        if (kind=='ordinary' and has_verify_button and e['tag']=='input'
                and e['type'] in ('number','tel','text')
                and re.search(r'\b(?:code|passcode|pin|digits)\b',e['label'],re.I)
                and not re.search(r'postal|zip|country|coupon|discount',e['label'],re.I)):
            kind='human_input';e['auth_kind']='otp'
        if re.search(r'verify.*(?:you are|you.re) human|i am not a robot',e['label'],re.I):kind='captcha_widget'
        if re.search(r'captcha|recaptcha|hcaptcha|turnstile',e.get('frame_url',''),re.I):
            kind='human_input' if e['tag'] in ('input','textarea') and e['type'] not in ('checkbox','radio','button','submit') else 'captcha_widget'
        e['category']=kind
        if kind=='captcha_widget':e['risk']='human_auth'
        elif kind=='human_input':e['risk']='human_auth';e['redacted']=True
        elif kind in ('final','final_unknown'):e['risk']='irreversible'
        elif kind in ('otp_send','otp_verify','captcha_refresh','auth_submit'):e['risk']='human_auth'
        elif kind=='upload_step':e['risk']='intermediate'
        # Next/Save Draft remain ordinary controls, but POST remains reviewed.
    return elements,targets,frames,truncated


def verification_page(text,title=''):
    return bool(re.search(r'checking your browser|verify (?:that )?you are human|performing security verification|attention required|access denied|unusual traffic|sorry.*automated|robot check',text,re.I) or re.search(r'just a moment|access denied|attention required',title,re.I))


def retain_private_value(session,value):
    if not value:return
    if len(value)>100:raise HTTPException(422,'Verification values must be at most 100 characters')
    if value not in session.private_values and len(session.private_values)>=100:raise HTTPException(429,'Verification value limit reached; reconcile and close this session')
    session.private_values.add(value)


def target_signature(element):
    return {k:v for k,v in element.items() if k not in ('bounds','in_viewport','validation_message','description','upload_hint','occluded','blocker','requires_scroll')}


async def signature(session):
    elements,targets,frames,truncated=await census(session)
    # Include visible semantic text in freshness check, not only controls:
    # a site may replace the review content without modifying inputs/buttons.
    try:visible=await asyncio.wait_for(session.page.locator('body').inner_text(timeout=2000),2.5)
    except (BrowserError,asyncio.TimeoutError):visible=''
    session.last_title='Unavailable'
    try:session.last_title=await asyncio.wait_for(session.page.title(),2)
    except (BrowserError,asyncio.TimeoutError):pass
    session.last_visible_text=visible
    fingerprint=hashlib.sha256(json.dumps({'url':session.page.url,'elements':elements,'frames':frames,
        'visible_text_sha256':hashlib.sha256(visible[:30000].encode()).hexdigest()},sort_keys=True).encode()).hexdigest()
    return fingerprint,elements,targets,frames,truncated


async def observe(session,screenshot=True):
    session.last_used=time.time()
    if not session.context.pages:raise HTTPException(410,'Browser session ended; reopen explicitly and reauthenticate',headers={'X-Browser-Outcome':'not_applied'})
    if session.page.is_closed():raise HTTPException(409,'Active tab is closed; switch to an observed live tab')
    if not session.permitted(session.page.url):
        if session.page.url.startswith('chrome-error://'):
            session.targets={};session.last_elements={};session.observation_id=str(uuid.uuid4());session.observed_at=time.time()
            return {'version':'2','context_id':session.id,'generation':session.generation,'observation_id':session.observation_id,
                    'url':'chrome-error://chromewebdata/','title':'Browser navigation failed','observed_at':session.observed_at,
                    'viewport':session.page.viewport_size,'elements':[],'frames':[],'tabs':[],
                    'structure':{'headings':[],'alerts':[],'tables':[]},'text':'Navigation failed or was blocked by browser policy.',
                    'accessibility':'','dialogs':session.dialogs[-10:],'screenshot_base64':'','screenshot_mime':'image/jpeg',
                    'preview_available':False,'page_status':'navigation_error','http_status':None,'truncated':False,
                    'waiting_human':False,'human_signals':[],'content_trust':'untrusted_website_data','policy':{},
                    'warnings':['Inspect the prior action outcome before retrying; no controls are exposed from this error page.']}
        raise HTTPException(403,'Active page left the configured origin policy')
    fingerprint,elements,targets,frames,truncated=await signature(session)
    session.observed_url=session.page.url
    session.last_navigation_status=session.navigation_statuses.get(session.page)
    session.last_elements={e['ref']:e for e in elements}
    session.targets=targets;session.fingerprint=fingerprint;session.observation_id=str(uuid.uuid4());session.observed_at=time.time()
    masks=[targets[e['ref']] for e in elements if e['redacted'] and e['category']!='captcha_widget']
    screenshot_bytes=b'';screenshot_error=None
    if screenshot:
        try:screenshot_bytes=await session.page.screenshot(type='jpeg',quality=55,mask=masks,animations='disabled',timeout=2500)
        except BrowserError:screenshot_error='Preview capture unavailable; structured observation remains available'
    private_values=list(session.private_values)
    for e in elements:
        if e['redacted'] and e['tag'] in ('input','textarea','select'):
            try:
                value=await targets[e['ref']].input_value()
                if value:private_values.append(value)
            except BrowserError:pass
    visible_text=session.last_visible_text[:12000]
    try:accessibility=(await asyncio.wait_for(session.page.locator('body').aria_snapshot(timeout=2000),2.5))[:16000]
    except (BrowserError,asyncio.TimeoutError):accessibility=''
    def scrub(text):
        for secret in sorted(private_values,key=len,reverse=True):
            text=re.sub(r'(?<!\w)'+re.escape(secret)+r'(?!\w)','[redacted]',text) if len(secret)<4 else text.replace(secret,'[redacted]')
        return text
    visible_text=scrub(visible_text);accessibility=scrub(accessibility)
    # Text/ARIA omit values by collecting descriptive document structure separately.
    try:structure=await asyncio.wait_for(session.page.locator('body').evaluate('''e=>({headings:[...e.querySelectorAll('h1,h2,h3,[role=heading]')].slice(0,50).map(x=>x.innerText.slice(0,300)),alerts:[...e.querySelectorAll('[role=alert],[aria-live=assertive]')].slice(0,20).map(x=>x.innerText.slice(0,500)),tables:[...e.querySelectorAll('table')].slice(0,5).map(t=>[...t.rows].slice(0,20).map(r=>[...r.cells].slice(0,12).map(c=>c.innerText.slice(0,300))))})'''),2.5)
    except (BrowserError,asyncio.TimeoutError):structure={'headings':[],'alerts':[],'tables':[]}
    # Conservative patterns mask common numeric identifiers in visible structure too.
    def redact(value):
        if isinstance(value,str):
            value=scrub(value)
            return re.sub(r'\b\d[\d -]{10,}\d\b','[redacted identifier]',value)
        if isinstance(value,list):return [redact(v) for v in value]
        if isinstance(value,dict):return {k:(v if k in ('ref','frame_id','context_id','observation_id','generation','tab_id','id','category','risk','type','tag','role','form_method','content_trust') else redact(v)) for k,v in value.items()}
        return value
    try:
        overlays=await asyncio.wait_for(session.page.locator('dialog[open],[role=dialog],[role=alertdialog],[role=listbox],[role=menu],iframe[title*=consent i],iframe[title*=privacy i]').evaluate_all("nodes=>nodes.filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&getComputedStyle(e).visibility!=='hidden'&&(e.tagName!=='IFRAME'||r.width>=200&&r.height>=100&&r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth)}).slice(0,10).map(e=>({id:e.id||e.getAttribute('aria-label')||e.tagName.toLowerCase(),label:(e.getAttribute('aria-label')||e.getAttribute('title')||e.querySelector('h1,h2,h3')?.textContent||'').slice(0,200),role:e.getAttribute('role')||e.tagName.toLowerCase(),requires_human:/cookie|consent|privacy|captcha|verification|sign in|log in/i.test((e.getAttribute('aria-label')||e.getAttribute('title')||'')+' '+(e.innerText||'').slice(0,2000)),modal:e.matches(':modal')||e.getAttribute('aria-modal')==='true'}))"),2)
    except (BrowserError,asyncio.TimeoutError):overlays=[]
    consent_pending=any(o.get('requires_human') and re.search(r'consent|privacy|cookie',o.get('label',''),re.I) for o in overlays)
    session.consent_required=consent_pending
    tabs=[]
    for page in session.context.pages[:20]:
        if not page.is_closed():tabs.append({'id':session.tab_id(page),'url':safe_url(page.url),'active':page==session.page,'allowed':session.permitted(page.url)})
    human_signals=[{'kind':'authentication_control','target_ref':e['ref']} for e in elements if e['risk']=='human_auth']
    for f in frames:
        if re.search(r'captcha|turnstile|face.?auth',f['url'],re.I):human_signals.append({'kind':'challenge_frame','frame_id':f['id']})
    blocked=verification_page(visible_text,session.last_title)
    page_status='inspection_incomplete' if session.inspection_incomplete else ('blocked' if blocked else ('http_error' if (session.last_navigation_status or 200)>=400 else ('loading_or_empty' if not elements and not visible_text.strip() else 'ready')))
    if consent_pending:human_signals.append({'kind':'consent_required','action':'citizen_choice_required','automatic_choice':False})
    if blocked:human_signals.append({'kind':'site_verification_interstitial','action':'human_review_required'})
    return {'consent_required':consent_pending,'downloads_started_total':session.download_events,'interaction_state':{'overlays':redact(overlays),'guidance':'Inspect open overlays before background controls; do not infer consent or dismiss security challenges.'},'version':'2','page_status':page_status,'http_status':session.last_navigation_status,'coverage':{'link_offset':session.link_offset,'link_query':session.link_query,'visible_link_limit':160,'max_elements':250},'context_id':session.id,'generation':session.generation,'observation_id':session.observation_id,'url':safe_url(session.page.url),'title':session.last_title,'observed_at':session.observed_at,'viewport':session.page.viewport_size,'elements':redact(elements),'frames':redact(frames),'tabs':redact(tabs),'structure':redact(structure),'text':redact(visible_text),'accessibility':redact(accessibility),'dialogs':session.dialogs[-10:],'screenshot_base64':base64.b64encode(screenshot_bytes).decode(),'screenshot_mime':'image/jpeg','preview_available':bool(screenshot_bytes),'truncated':truncated,'waiting_human':bool(human_signals),'human_signals':human_signals,'content_trust':'untrusted_website_data','policy':{'generic_submit':False,'origins':sorted(session.allowed) if not session.public_web else ['public-https-only'], 'navigation_mode':'public-web' if session.public_web else 'allowlist','network_methods':['GET','HEAD','OPTIONS']+(['POST'] if intermediate_post_permitted(session.page.url,public_web=session.public_web) else [])},'warnings':['No model is connected by this endpoint. Core must interpret these observations.']+([screenshot_error] if screenshot_error else [])}


async def resolve_target(session,element,targets=None):
    """Bind the verified DOM object; do not click a mutable nth() position."""
    target=(targets if targets is not None else session.targets).get(element['ref'])
    if target is None:raise HTTPException(409,'Target no longer observed; take a new snapshot')
    if not element.get('node_identity'):return target  # legacy isolated fixtures
    handle=await target.element_handle(timeout=1000) if hasattr(target,'element_handle') else target
    if handle is None or not await handle.evaluate("(e,id)=>globalThis[Symbol.for('next-wave.browser-observer.identity.v1')]?.objects.get(e)===id",element['node_identity']):
        raise HTTPException(409,'Target changed; observe and re-ground the action',headers={'X-Browser-Outcome':'not_applied'})
    return handle


async def act(session,req:BrowserAction,upload=None,capture_screenshot=True):
    session.last_effect_started=False
    fingerprint=hashlib.sha256(req.model_dump_json().encode()).hexdigest()
    previous=session.action_results.get(req.action_id)
    if previous:
        if previous[0]!=fingerprint:raise HTTPException(409,'Action ID reused with changed input')
        if previous[1] is None:raise HTTPException(409,'Previous action outcome is unknown; observe/reconcile before retrying')
        return previous[1]
    if req.observation_id!=session.observation_id or time.time()-session.observed_at>30:
        raise HTTPException(409,'Observation is stale; observe the page again')
    current,current_elements,_,_,_=await signature(session)
    if session.inspection_incomplete:raise HTTPException(503,'Page inspection incomplete; wait or request human review',headers={'X-Browser-Outcome':'not_applied'})
    if getattr(session,'consent_required',False) and req.kind not in ('navigate','back','wait','scroll','switch_tab','extract'):
        raise HTTPException(409,'Citizen consent choice required; do not click through the consent overlay',headers={'X-Browser-Outcome':'not_applied'})
    if verification_page(session.last_visible_text) and req.kind not in ('navigate','back','wait','scroll','switch_tab','extract'):
        raise HTTPException(403,'Site verification requires human assistance; automatic challenge interaction is unavailable')
    if current!=session.fingerprint:
        old=session.last_elements.get(req.target_ref) if req.target_ref else None
        fresh=next((e for e in current_elements if e['ref']==req.target_ref),None)
        target_stable=old is not None and fresh is not None and target_signature(old)==target_signature(fresh) and fresh['risk']!='irreversible' and session.page.url==session.observed_url
        if not target_stable and req.kind not in ('navigate','back','scroll','wait','switch_tab'):
            raise HTTPException(409,'Page changed since observation; observe and re-ground the action')
    element=None;loc=None
    if req.kind in ('click','fill','select','check','upload','extract','blur'):
        if not req.target_ref or req.target_ref not in session.targets:raise HTTPException(422,'An observed target_ref is required')
        _,elements,current_targets,_,_=await signature(session)
        element=next((e for e in elements if e['ref']==req.target_ref),None)
        old=session.last_elements.get(req.target_ref)
        if not element or not old or target_signature(element)!=target_signature(old):raise HTTPException(409,'Target changed; observe and re-ground the action')
        loc=await resolve_target(session,element,current_targets)
        upload_confirmation=req.kind=='click' and element.get('category')=='upload_step'
        if upload_confirmation:
            attached=any(e.get('type')=='file' and e.get('file_count') and (e.get('frame_id'),e.get('form_index'))==(element.get('frame_id'),element.get('form_index')) for e in elements)
            if not attached:raise HTTPException(409,'Attach a document to this upload form first')
            if not element.get('form_upload_only') and not intermediate_post_permitted(session.page.url,public_web=session.public_web):raise HTTPException(403,'Upload confirmation requires a reviewed form or portal adapter')
        if req.kind!='extract' and ((element['risk']!='ordinary' and not upload_confirmation) or element['disabled']):raise HTTPException(403,'Target requires a dedicated human/approval adapter or is disabled')
        if req.kind in ('fill','select','check','upload') and (not req.verified or not req.source_ref):raise HTTPException(422,'Verified input and source_ref are required')
        if req.kind=='click' and (element['type'] in ('checkbox','radio') or element['role'] in ('checkbox','radio','option','gridcell')) and (not req.verified or not req.source_ref):raise HTTPException(422,'Data-changing checkbox/radio clicks require a verified source')
    if req.kind=='navigate':
        await session.check_destination(req.url)
        if IRREVERSIBLE.search(urlsplit(req.url).path+' '+urlsplit(req.url).query):raise HTTPException(403,'Navigation destination resembles an irreversible action')
    if req.kind=='blur' and (element['tag'] not in ('input','textarea','select') and not element.get('contenteditable')):raise HTTPException(422,'Blur requires an observed editable control')
    if req.kind=='fill' and (element['tag'] not in ('input','textarea') and not element['contenteditable'] or element['type'] in ('file','checkbox','radio','button','submit') or element['readonly']):raise HTTPException(422,'Target is not an editable text field')
    if req.kind=='select' and element['tag']!='select':raise HTTPException(422,'Target is not a select control')
    if req.kind=='check' and element['type'] not in ('checkbox','radio'):raise HTTPException(422,'Target is not a checkbox/radio')
    if req.kind=='upload' and (element['type']!='file' or upload is None):raise HTTPException(422,'Resolve an authorized artifact before upload')
    if req.kind=='upload' and element['accept']:
        accepted=[a.strip().lower() for a in element['accept'].split(',')]
        extension='.'+upload['name'].rsplit('.',1)[-1].lower()
        mime=upload['mimeType']
        if not any(a in (extension,mime,'*/*') or (a.endswith('/*') and mime.startswith(a[:-1])) for a in accepted):
            raise HTTPException(422,'Prepared artifact does not match the observed upload accept constraint')
    if req.kind=='click' and element.get('category')=='search':
        from browser.search import search_scope
        search_scope(session.page.url,element)
    if req.kind=='click':
        if element['tag']=='a' and (not session.permitted(element['href']) or IRREVERSIBLE.search(element['href'])):raise HTTPException(403,'Link destination requires dedicated approval or is not allowlisted')
        try:
            if element.get('requires_scroll'):await loc.scroll_into_view_if_needed(timeout=min(req.timeout_ms,2500))
            await loc.click(trial=True,timeout=min(req.timeout_ms,3500))
        except BrowserError:raise HTTPException(409,'Target is not currently actionable; resolve any overlay or refresh the observation',headers={'X-Browser-Outcome':'not_applied'}) from None
    session.action_results[req.action_id]=(fingerprint,None)
    session.last_effect_started=True
    try:
        extracted=None
        before_url=session.page.url;before_tabs=set(session.context.pages);before_text=session.last_visible_text;before_downloads=session.download_events
        if req.kind=='click':
            if element.get('category')=='search':
                from browser.search import search_scope
                from browser.native_submit import click_reviewed_submit
                await click_reviewed_submit(session,loc,search_scope(session.page.url,element))
            elif element.get('category')=='upload_step' and element.get('form_upload_only'):
                from browser.interactions import scoped_interaction
                await scoped_interaction(session,loc,'upload_form',post_target=element['form_action'])
            else:await loc.click(timeout=req.timeout_ms)
        elif req.kind=='blur':await loc.evaluate('e=>e.blur()')
        elif req.kind=='fill':await loc.fill(req.value,timeout=req.timeout_ms)
        elif req.kind=='select':await loc.select_option(value=req.values if req.values else req.value,timeout=req.timeout_ms)
        elif req.kind=='check':await loc.set_checked(req.checked,timeout=req.timeout_ms)
        elif req.kind=='upload':await loc.set_input_files(upload,timeout=req.timeout_ms)
        elif req.kind=='navigate':await session.page.goto(req.url,wait_until='domcontentloaded',timeout=req.timeout_ms)
        elif req.kind=='back':
            # Unknown history may point outside policy; route interception still fails closed.
            await session.page.go_back(wait_until='domcontentloaded',timeout=req.timeout_ms)
        elif req.kind=='scroll':await session.page.mouse.wheel(0,req.scroll_y)
        elif req.kind=='wait':await asyncio.sleep(min(req.timeout_ms/1000,2))
        elif req.kind=='switch_tab':
            matches=[p for p in session.context.pages if not p.is_closed() and session.tab_id(p)==req.tab_id and session.permitted(p.url)]
            if len(matches)!=1:raise HTTPException(422,'Select a permitted observed tab')
            session.page=matches[0]
        elif req.kind=='extract':extracted={k:element[k] for k in ('ref','frame_id','label','value','options','required','redacted')}
        if req.kind in ('navigate','click','back'):
            if req.kind=='click':await asyncio.sleep(.1)
            try:await session.page.wait_for_load_state('domcontentloaded',timeout=2000)
            except BrowserError:pass
        effect={'check':'observation_required','matched':None}
        if req.kind=='fill':
            actual=await loc.inner_text() if element['contenteditable'] else await loc.input_value()
            effect={'check':'field_readback','matched':actual==req.value}
        elif req.kind=='select':
            actual=await loc.evaluate('e=>[...e.selectedOptions].map(o=>o.value)')
            effect={'check':'selection_readback','matched':sorted(actual)==sorted(req.values or [req.value])}
        elif req.kind=='check':effect={'check':'checked_readback','matched':await loc.is_checked()==req.checked}
        elif req.kind=='upload':effect={'check':'file_attachment','matched':await loc.evaluate('e=>e.files.length')>0}
        if req.kind=='click' and element.get('tag')=='a' and element.get('href') and element['href']!=safe_url(before_url):
            try:await session.page.wait_for_url(lambda url:str(url)!=before_url,timeout=min(req.timeout_ms,2000),wait_until='domcontentloaded')
            except BrowserError:pass
        after=await observe(session,screenshot=capture_screenshot)
        if req.kind in ('click','navigate','back','switch_tab','wait','blur'):
            new_tabs=[t for t in after.get('tabs',[]) if any(session.tab_id(p)==t['id'] for p in session.context.pages if p not in before_tabs)]
            effect={'check':'interaction_observation','matched':None,'url_changed':session.page.url!=before_url,'new_tabs':new_tabs,'downloads_started':session.download_events-before_downloads,'content_changed':session.last_visible_text!=before_text,'page_status':after.get('page_status'),'validation_errors':[e['validation_message'] for e in after['elements'] if e.get('validation_message')][:20],'confirmed_by_portal':False}
            if req.kind=='click' and element.get('role') in ('option','tab'):
                try:effect['matched']=await loc.evaluate("e=>e.getAttribute('aria-selected')")=='true'
                except BrowserError:pass
            if after.get('page_status')!='ready':effect['outcome']='requires_inspection'
        provenance={'target_ref':req.target_ref,'label':element['label'] if element else None,'source_ref':req.source_ref,'verified':req.verified} if req.kind in ('fill','select','check','upload') else None
        result={'action_id':req.action_id,'kind':req.kind,'status':'observed','effect':effect,'provenance':provenance,'extracted':extracted,'observation':after,'replayed':False}
        session.action_results[req.action_id]=(fingerprint,result)
        # Do not retain an unbounded history of large screenshots.
        if len(session.action_results)>30:session.action_results.pop(next(iter(session.action_results)))
        return result
    except BrowserError:
        raise HTTPException(409,'Browser action failed or timed out; observe before deciding whether to retry')
