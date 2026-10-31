"""Core-controlled access administration; no built-in citizen account directory."""
import hashlib
import os
import time
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from server.security import initialize_access, verify

router=APIRouter()

class Assignment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    subject: str=Field(min_length=1,max_length=100)
    ttl_seconds: int=Field(default=600,ge=30,le=3600)

class Revocation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    subject: str=Field(min_length=1,max_length=100)


@router.post('/integration/v1/identity/revoke')
async def revoke(req:Revocation,x_internal_key:str|None=Header(None)):
    from server.integration import api,require_service
    require_service(x_internal_key);initialize_access()
    with api().conn() as db:
        db.execute('INSERT INTO subject_epochs VALUES(?,?) ON CONFLICT(subject) DO UPDATE SET revoked_before=excluded.revoked_before',(req.subject,time.time()))
        db.execute('DELETE FROM operator_assignments WHERE subject=?',(req.subject,))
    return {'revoked':True}


@router.post('/integration/v1/sessions/{sid}/operators')
async def assign(sid:str,req:Assignment,x_internal_key:str|None=Header(None)):
    from server.integration import api,require_service
    require_service(x_internal_key)
    try:api().row(sid)
    except HTTPException as exc:
        if exc.status_code!=404:raise
        from server.browser_v2 import context,initialize
        initialize();context(sid)
    initialize_access()
    expires=time.time()+req.ttl_seconds
    with api().conn() as db:
        db.execute('INSERT INTO operator_assignments VALUES(?,?,?) ON CONFLICT(session_id,subject) DO UPDATE SET expires=excluded.expires',(sid,req.subject,expires))
    api().audit(sid,'operator_assigned','Read-only operator access granted')
    return {'expires_at':expires,'permissions':['read']}


@router.delete('/integration/v1/sessions/{sid}/operators/{subject}')
async def unassign(sid:str,subject:str,x_internal_key:str|None=Header(None)):
    from server.integration import api,require_service
    require_service(x_internal_key);initialize_access()
    with api().conn() as db:
        db.execute('DELETE FROM operator_assignments WHERE session_id=? AND subject=?',(sid,subject))
    return {'revoked':True}


@router.post('/auth/session')
async def exchange(request:Request):
    if os.getenv('SECURITY_MODE')!='signed' or not request.headers.get('authorization','').startswith('Bearer '):
        raise HTTPException(401,'Use a core-issued identity assertion to establish a session')
    # Security middleware has already verified expiry, revocation, audience and signature.
    token=request.headers['authorization'][7:]
    claims=verify(token,os.environ['IDENTITY_SIGNING_KEY'])
    response=JSONResponse({'subject':claims['sub'],'role':claims['role'],'expires_at':claims['exp']})
    response.set_cookie('gz_identity',token,max_age=max(0,int(claims['exp']-time.time())),httponly=True,secure=True,samesite='strict',path='/')
    return response


@router.post('/auth/logout')
async def logout(request:Request):
    from server.integration import api
    token=request.cookies.get('gz_identity','') or request.headers.get('authorization','').removeprefix('Bearer ')
    claims=verify(token,os.environ.get('IDENTITY_SIGNING_KEY',''))
    initialize_access()
    with api().conn() as db:
        db.execute('INSERT OR REPLACE INTO revoked_assertions VALUES(?,?)',(hashlib.sha256(token.encode()).hexdigest(),claims['exp']))
    response=JSONResponse({'signed_out':True});response.delete_cookie('gz_identity',path='/')
    return response
