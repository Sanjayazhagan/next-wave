"""General observed-page execution, independent of the fictional portal adapter.

Core supplies model decisions. This module never calls an AI, solves a challenge,
infers applicant data or permits generic final form submission.
"""
import asyncio
import base64
from dataclasses import dataclass,field
import hashlib
import json
import re
import time
import uuid
from urllib.parse import urlsplit,urlunsplit
from fastapi import HTTPException
from playwright.async_api import Error as BrowserError
from browser.protocol import BrowserAction

CONTROLS='a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[role=checkbox],[contenteditable=true]'
AUTH=re.compile(r'password|one.?time|\botp\b|captcha|verification code|security code|face.?auth',re.I)
IDENTIFIER=re.compile(r'aadhaar|aadhar|bank|account.?number|card.?number|passport|national.?id|cc-number',re.I)
IRREVERSIBLE=re.compile(r'submit|finali[sz]e|confirm|pay\b|purchase|delete|remove.?account|sign.?out|logout|approve|apply.?now|register|send.?otp',re.I)


def origin(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('Only configured HTTP(S) origins without URL credentials are accepted')
    return f'{p.scheme}://{p.hostname.lower()}:{p.port or (443 if p.scheme=="https" else 80)}'


def safe_url(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))


@dataclass
class GeneralContext:
    context:object
    page:object
    allowed:set[str]
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

    def permitted(self,url):
        try:return origin(url) in self.allowed
        except ValueError:return False

    async def route(self,route):
        if self.permitted(route.request.url) and route.request.method in ('GET','HEAD','OPTIONS') and not IRREVERSIBLE.search(urlsplit(route.request.url).path+' '+urlsplit(route.request.url).query):return await route.continue_()
        return await route.abort('blockedbyclient')

    def tab_id(self,page):
        if page not in self.tab_ids:self.tab_ids[page]=str(uuid.uuid4())
        return self.tab_ids[page]


async def census(session):
    """Bounded DOM/accessible controls, including permitted frames and open shadow roots."""
    elements=[];targets={};frames=[];truncated=False
    for frame_index,frame in enumerate(session.page.frames[:12]):
        frame_id=f'frame-{frame_index}'
        allowed=session.permitted(frame.url) or (frame.url in ('about:blank','about:srcdoc') and frame==session.page.main_frame)
        frames.append({'id':frame_id,'url':safe_url(frame.url),'available':allowed})
        if not allowed:continue
        controls=frame.locator(CONTROLS)
        count=await controls.count()
        for index in range(min(count,250-len(elements))):
            loc=controls.nth(index)
            if not await loc.is_visible():continue
            data=await loc.evaluate(r'''e=>({tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',role:e.getAttribute('role')||'',label:(e.labels?[...e.labels].map(x=>x.innerText).join(' '):'')||e.getAttribute('aria-label')||e.getAttribute('title')||e.getAttribute('placeholder')||e.innerText||e.getAttribute('name')||'',name:e.getAttribute('name')||'',required:e.required||e.getAttribute('aria-required')==='true',disabled:e.disabled||e.getAttribute('aria-disabled')==='true',value:e.type==='file'?'':(e.value||(e.isContentEditable?e.innerText:'')),href:e.getAttribute('href')||'',options:e.tagName==='SELECT'?[...e.options].slice(0,80).map(o=>({value:o.value,label:o.text,disabled:o.disabled})):[],checked:!!e.checked,form:!!e.form,accept:e.getAttribute('accept')||'',autocomplete:e.getAttribute('autocomplete')||'',readonly:!!e.readOnly,multiple:!!e.multiple,min:e.getAttribute('min'),max:e.getAttribute('max'),maxlength:e.getAttribute('maxlength'),pattern:e.getAttribute('pattern'),description:(e.getAttribute('aria-describedby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.innerText||'').join(' ').slice(0,500),validation_message:e.validationMessage||'',file_count:e.files?.length||0,contenteditable:e.isContentEditable})''')
            data['label']=data['label'].strip()[:300];data['name']=data['name'][:100]
            description=' '.join((data['label'],data['name'],data['type'],data['autocomplete']))
            sensitive=bool(AUTH.search(description));private=bool(IDENTIFIER.search(description))
            risk='human_auth' if sensitive else ('irreversible' if IRREVERSIBLE.search(description+' '+data['href']) or (data['tag']=='button' and data['form'] and data['type']!='button') or data['type'] in ('submit','image') else 'ordinary')
            ref=f'{frame_id}-element-{index}'
            data.update(ref=ref,frame_id=frame_id,risk=risk,redacted=sensitive or private)
            box=await loc.bounding_box()
            viewport=session.page.viewport_size or {'width':1180,'height':760}
            data['bounds']=box
            data['in_viewport']=bool(box and box['x']+box['width']>0 and box['y']+box['height']>0 and box['x']<viewport['width'] and box['y']<viewport['height'])
            if data['redacted']:data['value']='[redacted]'
            else:data['value']=str(data['value'])[:500]
            if data['href']:
                from urllib.parse import urljoin
                data['href']=safe_url(urljoin(frame.url,data['href']))
            targets[ref]=loc;elements.append(data)
        if count>250-len(elements) or len(elements)>=250:
            truncated=True
            if len(elements)>=250:break
    return elements,targets,frames,truncated


async def signature(session):
    elements,targets,frames,truncated=await census(session)
    fingerprint=hashlib.sha256(json.dumps({'url':session.page.url,'elements':elements,'frames':frames},sort_keys=True).encode()).hexdigest()
    return fingerprint,elements,targets,frames,truncated


async def observe(session):
    session.last_used=time.time()
    if session.page.is_closed():raise HTTPException(409,'Active tab is closed; switch to an observed live tab')
    if not session.permitted(session.page.url):raise HTTPException(403,'Active page left the configured origin policy')
    fingerprint,elements,targets,frames,truncated=await signature(session)
    session.targets=targets;session.fingerprint=fingerprint;session.observation_id=str(uuid.uuid4());session.observed_at=time.time()
    masks=[targets[e['ref']] for e in elements if e['redacted']]
    screenshot=await session.page.screenshot(type='jpeg',quality=55,mask=masks,animations='disabled')
    private_values=[]
    for e in elements:
        if e['redacted'] and e['tag'] in ('input','textarea','select'):
            try:
                value=await targets[e['ref']].input_value()
                if value:private_values.append(value)
            except BrowserError:pass
    visible_text=(await session.page.locator('body').inner_text())[:12000]
    accessibility=(await session.page.locator('body').aria_snapshot(timeout=5000))[:16000]
    for value in private_values:
        visible_text=visible_text.replace(value,'[redacted]');accessibility=accessibility.replace(value,'[redacted]')
    # Text/ARIA omit values by collecting descriptive document structure separately.
    structure=await session.page.locator('body').evaluate('''e=>({headings:[...e.querySelectorAll('h1,h2,h3,[role=heading]')].slice(0,50).map(x=>x.innerText.slice(0,300)),alerts:[...e.querySelectorAll('[role=alert],[aria-live=assertive]')].slice(0,20).map(x=>x.innerText.slice(0,500)),tables:[...e.querySelectorAll('table')].slice(0,5).map(t=>[...t.rows].slice(0,20).map(r=>[...r.cells].slice(0,12).map(c=>c.innerText.slice(0,300))))})''')
    # Conservative patterns mask common numeric identifiers in visible structure too.
    def redact(value):
        if isinstance(value,str):
            for secret in private_values:value=value.replace(secret,'[redacted]')
            return re.sub(r'\b\d[\d -]{10,}\d\b','[redacted identifier]',value)
        if isinstance(value,list):return [redact(v) for v in value]
        if isinstance(value,dict):return {k:redact(v) for k,v in value.items()}
        return value
    tabs=[]
    for page in session.context.pages[:20]:
        if not page.is_closed():tabs.append({'id':session.tab_id(page),'url':safe_url(page.url),'active':page==session.page,'allowed':session.permitted(page.url)})
    human_signals=[{'kind':'authentication_control','target_ref':e['ref']} for e in elements if e['risk']=='human_auth']
    for f in frames:
        if re.search(r'captcha|turnstile|face.?auth',f['url'],re.I):human_signals.append({'kind':'challenge_frame','frame_id':f['id']})
    return {'version':'2','context_id':session.id,'generation':session.generation,'observation_id':session.observation_id,'url':safe_url(session.page.url),'title':await session.page.title(),'observed_at':session.observed_at,'viewport':session.page.viewport_size,'elements':redact(elements),'frames':redact(frames),'tabs':redact(tabs),'structure':redact(structure),'text':redact(visible_text),'accessibility':redact(accessibility),'dialogs':session.dialogs[-10:],'screenshot_base64':base64.b64encode(screenshot).decode(),'screenshot_mime':'image/jpeg','truncated':truncated,'waiting_human':bool(human_signals),'human_signals':human_signals,'content_trust':'untrusted_website_data','policy':{'generic_submit':False,'origins':sorted(session.allowed),'network_methods':['GET','HEAD','OPTIONS']},'warnings':['No model is connected by this endpoint. Core must interpret these observations.']}


async def act(session,req:BrowserAction,upload=None):
    fingerprint=hashlib.sha256(req.model_dump_json().encode()).hexdigest()
    previous=session.action_results.get(req.action_id)
    if previous:
        if previous[0]!=fingerprint:raise HTTPException(409,'Action ID reused with changed input')
        if previous[1] is None:raise HTTPException(409,'Previous action outcome is unknown; observe/reconcile before retrying')
        return previous[1]
    if req.observation_id!=session.observation_id or time.time()-session.observed_at>30:
        raise HTTPException(409,'Observation is stale; observe the page again')
    current,_,_,_,_=await signature(session)
    if current!=session.fingerprint:raise HTTPException(409,'Page changed since observation; observe and re-ground the action')
    element=None;loc=None
    if req.kind in ('click','fill','select','check','upload','extract'):
        if not req.target_ref or req.target_ref not in session.targets:raise HTTPException(422,'An observed target_ref is required')
        _,elements,_,_,_=await signature(session)
        element=next(e for e in elements if e['ref']==req.target_ref);loc=session.targets[req.target_ref]
        if req.kind!='extract' and (element['risk']!='ordinary' or element['disabled']):raise HTTPException(403,'Target requires a dedicated human/approval adapter or is disabled')
        if req.kind in ('fill','select','check','upload') and (not req.verified or not req.source_ref):raise HTTPException(422,'Verified input and source_ref are required')
        if req.kind=='click' and (element['type'] in ('checkbox','radio') or element['role']=='checkbox') and (not req.verified or not req.source_ref):raise HTTPException(422,'Data-changing checkbox/radio clicks require a verified source')
    if req.kind=='navigate':
        if not session.permitted(req.url) or IRREVERSIBLE.search(urlsplit(req.url).path+' '+urlsplit(req.url).query):raise HTTPException(403,'Navigation destination is not a permitted read-only page')
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
    session.action_results[req.action_id]=(fingerprint,None)
    try:
        extracted=None
        if req.kind=='click':
            if element['tag']=='a' and (not session.permitted(element['href']) or IRREVERSIBLE.search(element['href'])):raise HTTPException(403,'Link destination requires dedicated approval or is not allowlisted')
            await loc.click(timeout=req.timeout_ms)
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
        after=await observe(session)
        provenance={'target_ref':req.target_ref,'label':element['label'] if element else None,'source_ref':req.source_ref,'verified':req.verified} if req.kind in ('fill','select','check','upload') else None
        result={'action_id':req.action_id,'kind':req.kind,'status':'observed','effect':effect,'provenance':provenance,'extracted':extracted,'observation':after,'replayed':False}
        session.action_results[req.action_id]=(fingerprint,result)
        # Do not retain an unbounded history of large screenshots.
        if len(session.action_results)>30:session.action_results.pop(next(iter(session.action_results)))
        return result
    except BrowserError:
        raise HTTPException(409,'Browser action failed or timed out; observe before deciding whether to retry')
