import json
import time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import server.app as app
from server.security import mint, verify


def test_identity_claims_and_tampering():
    key = 'identity-test-key-with-at-least-32-characters'
    token = mint('citizen-a', 'citizen', key)
    assert verify(token, key)['sub'] == 'citizen-a'
    with pytest.raises(HTTPException):
        verify(token+'tampered', key)
    with pytest.raises(HTTPException):
        verify(token, key+'wrong')


def test_core_contract_idempotency_and_identity_isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'DB', tmp_path/'core.db')
    monkeypatch.setenv('SECURITY_MODE', 'signed')
    from cryptography.fernet import Fernet
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    key = 'identity-test-key-with-at-least-32-characters'
    monkeypatch.setenv('IDENTITY_SIGNING_KEY', key)
    monkeypatch.setattr(app, 'KEY', 'service-test-key-with-at-least-32-characters')
    monkeypatch.setattr(app, 'SIGN_KEY', 'approval-test-key-with-at-least-32-characters')
    calls = []
    async def worker(method, path, payload=None, timeout=20):
        calls.append(path)
        if path == '/sessions':
            return {'worker_session_id':'worker-1'}
        if path.endswith('/otp'):
            return {'ok':True}
        raise AssertionError(path)
    monkeypatch.setattr(app, 'worker', worker)
    headers = {'X-Internal-Key':app.KEY}
    payload = {'request_id':'request-0001','subject':'alice','consent_ref':'consent-1','fields':{k:{'value':v,'source_ref':'synthetic-fixture','confidence':1,'verified':True} for k,v in app.DEFAULT_PROFILE.items()}}
    with TestClient(app.app) as c:
        assert c.post('/api/sessions',json={'consent':True}).status_code == 401
        first = c.post('/integration/v1/sessions',headers=headers,json=payload)
        assert first.status_code == 201, first.text
        sid = first.json()['id']
        assert c.post('/integration/v1/sessions',headers=headers,json=payload).json()['id'] == sid
        assert calls == ['/sessions']
        alice = {'Authorization':'Bearer '+mint('alice','citizen',key)}
        bob = {'Authorization':'Bearer '+mint('bob','citizen',key)}
        assert c.get('/api/sessions/'+sid,headers=alice).status_code == 200
        assert c.get('/api/sessions/'+sid,headers=bob).status_code == 403
        fields = c.get('/api/sessions/'+sid+'/fields',headers=alice).json()['fields']
        assert fields[0]['source_ref'] == 'synthetic-fixture'
        command = {'action_id':'action-0001','expected_state':'otp_needed','kind':'otp','payload':{'otp':'246810'}}
        one = c.post('/integration/v1/sessions/'+sid+'/commands',headers=headers,json=command)
        assert one.status_code == 200, one.text
        assert c.post('/integration/v1/sessions/'+sid+'/commands',headers=headers,json=command).json() == one.json()
        assert calls.count('/sessions/worker-1/otp') == 1
        with app.conn() as db:
            rows = str([tuple(r) for r in db.execute('SELECT * FROM core_commands')])
        assert '246810' not in rows


def test_uncertain_submission_reconciliation(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'DB', tmp_path/'reconcile.db')
    with TestClient(app.app) as c:
        with app.conn() as db:
            db.execute('INSERT INTO sessions(id,worker_id,state,profile,consent_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', ('stable-key','lost','submission_uncertain',json.dumps(app.DEFAULT_PROFILE),app.now(),app.now(),app.now()))
        assert c.post('/api/sessions/stable-key/resume').status_code == 409
        assert c.post('/api/sessions/stable-key/reconcile').status_code == 409
        receipt = c.post('/mock/api/submit',json={'idempotency_key':'stable-key'}).json()['receipt_id']
        result = c.post('/api/sessions/stable-key/reconcile').json()
        assert result['state'] == 'submitted'
        assert result['receipt_id'] == receipt
