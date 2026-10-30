import time
from fastapi.testclient import TestClient
import server.app as app


def test_scoped_handoff_and_event_replay(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'DB', tmp_path/'tasks.db')
    phase = {'challenge': True}

    async def worker(method, path, payload=None, timeout=20):
        if path == '/sessions':
            return {'worker_session_id': 'browser'}
        if path.endswith('/otp'):
            return {'ok': True}
        if path.endswith('/challenge'):
            return {'stage': 'challenge', 'screenshot_base64': '', 'mode': 'demo'}
        if path.endswith('/human'):
            ok = payload['challenge_answer'] == '7'
            phase['challenge'] = not ok
            return {'ok': ok}
        raise AssertionError(path)

    monkeypatch.setattr(app, 'worker', worker)
    headers = {'X-Internal-Key': app.KEY}
    with TestClient(app.app) as c:
        sid = c.post('/api/sessions', json={'consent': True}).json()['id']
        c.post(f'/api/sessions/{sid}/otp', json={'otp': '246810'})
        assert c.post('/integration/v1/human-tasks', json={'session_id': sid}).status_code == 401
        data = c.post('/integration/v1/human-tasks', headers=headers, json={'session_id': sid}).json()
        tid = data['task_id']; token = data['assistance_path'].split('#')[1]
        assert c.get('/assist/'+tid).status_code == 200
        assert c.get('/assist-api/'+tid+'/view').status_code == 403
        assert c.post(f'/api/sessions/{sid}/human', json={'challenge_answer': '7'}).status_code == 409
        assert c.post('/assist-api/'+tid+'/claim', json={'invitation': 'x'*32}).status_code == 403
        claim = c.post('/assist-api/'+tid+'/claim', json={'invitation': token}).json()
        assert c.post('/assist-api/'+tid+'/claim', json={'invitation': token}).status_code == 403
        auth = {'Authorization': 'Bearer '+claim['bearer']}
        assert c.get('/assist-api/'+tid+'/view', headers=auth).status_code == 200
        assert not c.post('/assist-api/'+tid+'/answer', headers=auth, json={'answer': 'wrong'}).json()['ok']
        assert c.post('/assist-api/'+tid+'/answer', headers=auth, json={'answer': '7'}).json()['ok']
        assert c.get('/assist-api/'+tid+'/view', headers=auth).status_code == 403
        events = c.get('/integration/v1/events/'+sid, headers=headers).json()
        assert any(e['kind'] == 'human_task_completed' for e in events['events'])
        assert c.get('/integration/v1/events/'+sid, headers=headers, params={'after': events['next_cursor']}).json()['events'] == []
        assert token not in str(events)
        assert claim['bearer'] not in str(events)


def test_expired_invitation(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'DB', tmp_path/'expired.db')
    from server.integration import initialize
    with TestClient(app.app) as c:
        initialize()
        with app.conn() as db:
            db.execute('INSERT INTO human_tasks VALUES(?,?,?,?,?,?,?,?)', ('expired', 'gone', 'gone', 'bad', None, time.time()-1, 'offered', 0))
        assert c.post('/assist-api/expired/claim', json={'invitation': 'x'*32}).status_code == 403
