"""Authenticated gateway for the main LangGraph agent, keeping Playwright private.

Configure main's BROWSER_WORKER_URL=https://browser.example/core-browser and
BROWSER_WORKER_KEY to the same INTERNAL_KEY as this service. No core app code
other than its HTTP client and approval call needs to change.
"""
from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter(prefix='/core-browser', tags=['LangGraph bridge'])

class Payload(BaseModel):
    model_config={'extra':'allow'}


def check(key):
    from server.integration import require_service
    require_service(key)

async def pass_through(method,path,payload=None):
    from server.app import worker
    return await worker(method,'/core'+path,payload,timeout=45)

@router.post('/session')
async def open_session(req:Payload,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('POST','/session',req.model_dump())

@router.post('/session/{sid}/login')
async def login(sid:str,req:Payload,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('POST',f'/session/{sid}/login',req.model_dump())

@router.get('/session/{sid}/snapshot')
async def snapshot(sid:str,x_internal_key:str|None=Header(None),link_offset:int=0,link_query:str=''):
    check(x_internal_key)
    from urllib.parse import urlencode
    return await pass_through('GET',f'/session/{sid}/snapshot?'+urlencode({'link_offset':link_offset,'link_query':link_query}))

@router.post('/session/{sid}/action')
async def action(sid:str,req:Payload,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('POST',f'/session/{sid}/action',req.model_dump())

@router.post('/session/{sid}/authorize-submit')
async def authorize(sid:str,req:Payload,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('POST',f'/session/{sid}/authorize-submit',req.model_dump())

@router.delete('/session/{sid}')
async def close(sid:str,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('DELETE',f'/session/{sid}')

@router.get('/session/{sid}/view')
async def view(sid:str,x_internal_key:str|None=Header(None)):
    check(x_internal_key)
    return await pass_through('GET',f'/session/{sid}/view')
