"""Authenticated general browser tools; separate from the scholarship demo flow."""
import asyncio
import base64
import os
import time
from typing import Literal
from fastapi import APIRouter,Header,HTTPException
from playwright.async_api import TimeoutError as PWTimeout, Error as PWError
from pydantic import Field
from browser.protocol import BrowserAction,ContextStart,StrictModel
from browser.general import GeneralContext,act,observe,origin,bound_tabs,watch_navigation,lock_guard
from browser.public_web import navigation_mode, NAV_MODE_PUBLIC, assert_public_url

router=APIRouter()
contexts:dict[str,GeneralContext]={}


def worker():
    from browser import worker as w
    return w


def get(ident):
    ctx=contexts.get(ident)
    if not ctx:raise HTTPException(404,'Browser context was lost or expired; create a new generation and reauthenticate')
    ctx.last_used=time.time();return ctx


class ToolAction(BrowserAction):
    file_base64:str=Field(default='',max_length=1400000)
    file_name:str=Field(default='prepared.pdf',pattern=r'^[A-Za-z0-9_.-]{1,100}\.(pdf|png|jpg|jpeg)$')
    file_mime:Literal['application/pdf','image/png','image/jpeg']='application/pdf'


@router.post('/contexts',status_code=201)
async def create(req:ContextStart,x_internal_key:str|None=Header(None)):
    w=worker();w.require_key(x_internal_key)
    dynamic = navigation_mode() == NAV_MODE_PUBLIC
    allowed={origin(u.strip()) for u in (os.getenv('BROWSER_ALLOWED_ORIGINS') or w.MOCK_URL).split(',') if u.strip()} if not dynamic else set()
    if dynamic:
        await assert_public_url(req.url)
    else:
        try:requested=origin(req.url)
        except ValueError:raise HTTPException(422,'Invalid navigation origin')
        if requested not in allowed:raise HTTPException(403,'Origin is not configured by the trusted operator')
    async with lock_guard(w.creation_lock,status=429):
        if len(w.sessions)+len(contexts)>=int(os.getenv('MAX_BROWSER_SESSIONS','8')):raise HTTPException(429,'Browser capacity reached')
        context=None
        try:
            context=await w.app.state.browser.new_context(viewport={'width':1180,'height':760},accept_downloads=False,service_workers='block')
            page=await context.new_page();session=GeneralContext(context=context,page=page,allowed=allowed,public_web=dynamic)
            bound_tabs(session);watch_navigation(session)
            await context.route('**/*',session.route)
            await context.route_web_socket('**/*',lambda socket:socket.close())
            async def dialog(d):
                session.dialogs.append({'kind':d.type,'disposition':'dismissed_for_safety','message_retained':False})
                session.dialogs=session.dialogs[-20:]
                await d.dismiss()
            context.on('page',lambda p:p.on('dialog',dialog));page.on('dialog',dialog)
            await page.goto(req.url,wait_until='domcontentloaded',timeout=15000)
            result=await observe(session)
        except BaseException as exc:
            if context is not None:
                try:await context.close()
                except Exception:pass
            if isinstance(exc,PWTimeout):raise HTTPException(504,'Browser navigation timed out; run worker navigation diagnostics') from None
            if isinstance(exc,PWError):raise HTTPException(502,'Browser setup or navigation failed; run worker navigation diagnostics') from None
            raise
        contexts[session.id]=session
        return result


@router.get('/contexts/{ident}/observe')
async def observation(ident:str,x_internal_key:str|None=Header(None),link_offset:int=0,link_query:str=''):
    worker().require_key(x_internal_key);session=get(ident)
    if not 0<=link_offset<=10000 or len(link_query)>120:raise HTTPException(422,'Invalid link query or offset')
    async with lock_guard(session.lock):
        session.link_offset=link_offset;session.link_query=link_query
        return await observe(session)

@router.get('/contexts/{ident}/view')
async def viewer(ident:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key);session=get(ident)
    async with lock_guard(session.lock):
        saved=(session.targets,session.observation_id,session.fingerprint,session.observed_at,session.last_elements,session.observed_url,session.last_visible_text)
        try:
            snapshot=await observe(session)
            return {k:v for k,v in snapshot.items() if k in ('version','context_id','generation','url','title','observed_at','screenshot_base64','screenshot_mime','text','structure','waiting_human','warnings')}
        finally:
            session.targets,session.observation_id,session.fingerprint,session.observed_at,session.last_elements,session.observed_url,session.last_visible_text=saved


@router.post('/contexts/{ident}/actions')
async def action(ident:str,req:ToolAction,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key);session=get(ident);upload=None
    if req.kind=='upload':
        try:raw=base64.b64decode(req.file_base64,validate=True)
        except Exception:raise HTTPException(422,'Invalid prepared artifact encoding')
        if len(raw)>1048576:raise HTTPException(422,'Prepared upload must be at most 1 MB')
        from browser.document_validation import validate_document
        validate_document(raw,req.file_name,req.file_mime)
        upload={'name':req.file_name,'mimeType':req.file_mime,'buffer':raw}
    # Never retain a file or secret payload in the worker's replay cache.
    command=BrowserAction.model_validate(req.model_dump(exclude={'file_base64','file_name','file_mime'}))
    async with lock_guard(session.lock):
        session.last_effect_started=False
        try:
            async with asyncio.timeout(35):return await act(session,command,upload)
        except asyncio.TimeoutError:
            raise HTTPException(504,'Browser operation budget exceeded; inspect the outcome before retrying',headers={'X-Browser-Outcome':'unknown' if session.last_effect_started else 'not_applied'}) from None
        except HTTPException as exc:
            raise HTTPException(exc.status_code,exc.detail,headers={'X-Browser-Outcome':'unknown' if session.last_effect_started else 'not_applied'}) from None


@router.delete('/contexts/{ident}')
async def close(ident:str,x_internal_key:str|None=Header(None)):
    worker().require_key(x_internal_key);session=contexts.get(ident)
    if session:
        async with lock_guard(session.lock):
            contexts.pop(ident,None);session.private_values.clear();await session.context.close()
    return {'closed':True}
