"""API-only tests: safe even where a managed Chromium policy forbids navigation."""
import importlib, os, tempfile
from fastapi.testclient import TestClient

def test_api_contract_and_guardrails(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'test.db'))
    # import module after setting demo database location
    import server.app as mod
    mod.DB=tmp_path/'test.db'
    with TestClient(mod.app) as client:
        assert client.get('/health').json()['real_portal_enabled'] is False
        assert client.post('/api/sessions',json={'consent':False}).status_code == 400
        assert client.post('/api/sessions',json={'consent':True,'portal':'real-NSP'}).status_code == 403
        assert client.get('/').status_code == 200
        assert 'FICTITIOUS SCHOLARSHIP' in client.get('/mock/').text
        r=client.post('/mock/api/submit',json={'idempotency_key':'test-unique-0001'})
        assert r.status_code == 200
        receipt=r.json()['receipt_id']
        assert receipt.startswith('MOCK-2026-')
        assert client.post('/mock/api/submit',json={'idempotency_key':'test-unique-0001'}).json()['receipt_id']==receipt
        assert client.get('/mock/api/status/'+receipt).json()['status']=='submitted'
        assert client.post('/mock/api/submit',json={'idempotency_key':'short'}).status_code==400
        assert client.get('/api/sessions/not-found').status_code==404

def test_approval_capability_signature():
    from browser.worker import expected_cap
    from server.app import SIGN_KEY
    import hashlib,hmac
    sid='known-synthetic-session';digest='0'*64;exp=12345
    actual=expected_cap(sid,digest,exp)
    assert actual==hmac.new(SIGN_KEY.encode(),f'{sid}:{digest}:{exp}'.encode(),hashlib.sha256).hexdigest()
    assert actual!=expected_cap('other-session',digest,exp)
