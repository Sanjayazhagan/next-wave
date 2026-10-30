"""Persisted profile recovery must invalidate approval and request human login."""
import json
from fastapi import HTTPException
from fastapi.testclient import TestClient
import server.app as mod


def test_lost_browser_recovery_and_edit_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, 'DB', tmp_path/'recovery.db')
    calls = []

    async def worker(method, path, payload=None, timeout=20):
        calls.append((method, path))
        if method == 'GET':
            raise HTTPException(404, 'No browser session')
        return {'worker_session_id': 'fresh-browser', 'stage': 'otp_needed'}

    monkeypatch.setattr(mod, 'worker', worker)
    with TestClient(mod.app) as client:
        with mod.conn() as db:
            db.execute('INSERT INTO sessions(id,worker_id,state,profile,consent_at,review_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       ('saved', 'lost-browser', 'approval_needed', json.dumps(mod.DEFAULT_PROFILE), mod.now(), 'old-digest', mod.now(), mod.now()))
        response = client.post('/api/sessions/saved/resume')
        assert response.status_code == 200
        assert response.json()['state'] == 'otp_needed'
        assert response.json()['review_hash'] is None
        assert json.loads(mod.row('saved')['profile']) == mod.DEFAULT_PROFILE
        assert client.post('/api/sessions/saved/approve', json={'confirmed': True, 'review_hash': 'old-digest'}).status_code == 409
        assert client.post('/api/sessions/saved/edit', json={'profile': mod.DEFAULT_PROFILE}).status_code == 409
        assert calls == [('GET', '/sessions/lost-browser/snapshot'), ('POST', '/sessions')]
