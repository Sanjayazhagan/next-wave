import asyncio
import base64
import json
import sqlite3
import time
from pathlib import Path
import httpx
import pytest
from cryptography.fernet import Fernet,InvalidToken
from fastapi.testclient import TestClient
import server.app as app
from server.storage import seal,unseal,pack,unpack,rotate,PREFIX
from server.security import mint
from scripts.database_ops import encrypted_backup,restore_backup


def test_encrypted_storage_rotation_backup_and_scope(monkeypatch,tmp_path):
    old=Fernet.generate_key().decode();new=Fernet.generate_key().decode()
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',old)
    encrypted=seal('private synthetic name','profile:test')
    assert 'private synthetic name' not in encrypted
    assert unseal(encrypted,'profile:test')=='private synthetic name'
    with pytest.raises(ValueError):unseal(encrypted,'profile:other')
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',new+','+old)
    rotated=rotate(encrypted)
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',new)
    assert unseal(rotated,'profile:test')=='private synthetic name'
    with pytest.raises(InvalidToken):unseal(encrypted,'profile:test')
    source=tmp_path/'source.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE demo(value TEXT)');db.execute('INSERT INTO demo VALUES(?)',('private synthetic name',))
    target=tmp_path/'backup.enc';restored=tmp_path/'restored.db'
    encrypted_backup(source,target)
    assert b'private synthetic name' not in target.read_bytes()
    restore_backup(target,restored)
    with sqlite3.connect(restored) as db:assert db.execute('SELECT value FROM demo').fetchone()[0]=='private synthetic name'
    with pytest.raises(ValueError):restore_backup(target,restored)
    corrupted=tmp_path/'corrupted.enc';corrupted.write_bytes(target.read_bytes()[:-4]+b'xxxx')
    with pytest.raises(InvalidToken):restore_backup(corrupted,tmp_path/'bad.db')


def test_encrypted_artifact_ownership_and_expiry(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'artifact.db');monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    async def worker(*args,**kwargs):return {'worker_session_id':'worker'}
    monkeypatch.setattr(app,'worker',worker)
    headers={'X-Internal-Key':app.KEY}
    with TestClient(app.app) as c:
        start={'request_id':'artifact-test-01','subject':'alice','consent_ref':'test','fields':{k:{'value':v,'source_ref':'test','confidence':1,'verified':True} for k,v in app.DEFAULT_PROFILE.items()}}
        sid=c.post('/integration/v1/sessions',json=start,headers=headers).json()['id']
        pdf=app.fixture_pdf();payload={'subject':'alice','source_ref':'synthetic-doc','file_name':'test.pdf','file_base64':base64.b64encode(pdf).decode()}
        path='/integration/v1/sessions/'+sid+'/artifacts'
        assert c.post(path,json={**payload,'subject':'bob'},headers=headers).status_code==403
        result=c.post(path,json=payload,headers=headers);assert result.status_code==201,result.text
        ident=result.json()['artifact_id']
        with app.conn() as db:
            raw=db.execute('SELECT body FROM artifacts WHERE id=?',(ident,)).fetchone()['body']
            profile=db.execute('SELECT profile FROM sessions WHERE id=?',(sid,)).fetchone()['profile']
        assert b'%PDF-' not in raw and app.DEFAULT_PROFILE['student_name'] not in profile
        assert c.get(path+'/'+ident,headers=headers).content==pdf
        assert c.get('/integration/v1/sessions/other/artifacts/'+ident,headers=headers).status_code==404
        c.delete(path+'/'+ident,headers=headers)
        assert c.get(path+'/'+ident,headers=headers).status_code==404


def test_revocation_operator_assignment_and_cookie_csrf(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'access.db')
    monkeypatch.setenv('SECURITY_MODE','signed');monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    key='identity-independent-key-for-access-testing'
    monkeypatch.setenv('IDENTITY_SIGNING_KEY',key)
    monkeypatch.setattr(app,'KEY','service-independent-key-for-access-testing')
    monkeypatch.setattr(app,'SIGN_KEY','approval-independent-key-for-access-testing')
    async def worker(*args,**kwargs):return {'worker_session_id':'worker'}
    monkeypatch.setattr(app,'worker',worker)
    service={'X-Internal-Key':app.KEY}
    with TestClient(app.app,base_url='https://testserver') as c:
        payload={'request_id':'access-test-01','subject':'alice','consent_ref':'test','fields':{k:{'value':v,'source_ref':'test','confidence':1,'verified':True} for k,v in app.DEFAULT_PROFILE.items()}}
        sid=c.post('/integration/v1/sessions',headers=service,json=payload).json()['id']
        operator={'Authorization':'Bearer '+mint('helper','operator',key)}
        assert c.get('/api/sessions/'+sid,headers=operator).status_code==403
        assert c.post('/integration/v1/sessions/'+sid+'/operators',headers=service,json={'subject':'helper'}).status_code==200
        assert c.get('/api/sessions/'+sid,headers=operator).status_code==200
        assert c.post('/api/sessions/'+sid+'/fill',headers=operator,json={}).status_code==403
        alice=mint('alice','citizen',key)
        response=c.post('/auth/session',headers={'Authorization':'Bearer '+alice})
        assert response.status_code==200
        cookie=response.headers['set-cookie'];assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
        assert c.post('/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403
        assert c.post('/auth/logout',headers={'Origin':'https://testserver'}).status_code==200
        assert c.get('/api/sessions/'+sid,headers={'Authorization':'Bearer '+alice}).status_code==401
        c.cookies.clear()
        assert c.post('/integration/v1/identity/revoke',headers=service,json={'subject':'helper'}).status_code==200
        assert c.get('/api/sessions/'+sid,headers=operator).status_code==401


@pytest.mark.asyncio
async def test_chunked_body_rejected_before_handler(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'body.db');monkeypatch.setenv('MAX_REQUEST_BYTES','256')
    touched=[]
    async def worker(*args,**kwargs):touched.append(True);raise AssertionError('Worker must not be called')
    monkeypatch.setattr(app,'worker',worker)
    with TestClient(app.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://testserver') as c:
            async def chunks():
                yield b'{'*200
                yield b'x'*200
            r=await c.post('/api/sessions',content=chunks(),headers={'Content-Type':'application/json'})
            assert r.status_code==413
    assert not touched
