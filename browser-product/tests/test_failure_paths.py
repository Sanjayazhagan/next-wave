import asyncio
import json
import time
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import server.app as app


@pytest.mark.asyncio
async def test_concurrent_core_commands_and_expired_lease(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'concurrent.db')
    entered=asyncio.Event();release=asyncio.Event();calls=[]
    async def worker(method,path,payload=None,timeout=20):
        calls.append(path)
        if path=='/sessions':return {'worker_session_id':'worker'}
        if path.endswith('/otp'):
            entered.set();await release.wait();return {'ok':True}
        raise AssertionError(path)
    monkeypatch.setattr(app,'worker',worker)
    headers={'X-Internal-Key':app.KEY}
    with TestClient(app.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://testserver',headers=headers) as c:
            sid=(await c.post('/api/sessions',json={'consent':True})).json()['id']
            with app.conn() as db:
                db.execute('CREATE TABLE IF NOT EXISTS execution_leases (session_id TEXT PRIMARY KEY,token TEXT,expires REAL)')
                db.execute('INSERT INTO execution_leases VALUES(?,?,?)',(sid,'expired',time.time()-1))
            command={'action_id':'concurrent-action-01','expected_state':'otp_needed','kind':'otp','payload':{'otp':'246810'}}
            first=asyncio.create_task(c.post('/integration/v1/sessions/'+sid+'/commands',json=command))
            await asyncio.wait_for(entered.wait(),3)
            try:
                second=await c.post('/integration/v1/sessions/'+sid+'/commands',json={**command,'action_id':'concurrent-action-02'})
                assert second.status_code==409
            finally:release.set()
            assert (await first).status_code==200
            assert calls.count('/sessions/worker/otp')==1


def test_timeout_after_portal_commit_reconciles_without_resubmit(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'uncertain.db')
    calls=[]
    async def worker(method,path,payload=None,timeout=20):
        calls.append(path)
        if path.endswith('/submit'):
            await app.mock_submit({'idempotency_key':'stable-synthetic-session'})
            raise HTTPException(504,'Synthetic response lost after portal commit')
        raise AssertionError(path)
    monkeypatch.setattr(app,'worker',worker)
    with TestClient(app.app) as c:
        with app.conn() as db:
            db.execute('INSERT INTO sessions(id,worker_id,state,profile,consent_at,review_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',('stable-synthetic-session','worker','approval_needed',json.dumps(app.DEFAULT_PROFILE),app.now(),'review-hash',app.now(),app.now()))
        path='/api/sessions/stable-synthetic-session'
        assert c.post(path+'/approve',json={'confirmed':True,'review_hash':'review-hash'}).status_code==504
        assert c.get(path).json()['state']=='submission_uncertain'
        assert c.post(path+'/approve',json={'confirmed':True,'review_hash':'review-hash'}).status_code==409
        assert c.post(path+'/reconcile').json()['state']=='submitted'
        assert len(calls)==1
        with app.conn() as db:assert db.execute('SELECT COUNT(*) FROM demo_receipts').fetchone()[0]==1
