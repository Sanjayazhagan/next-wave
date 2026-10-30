from fastapi.testclient import TestClient
import server.app as app


def test_auth_rate_and_protected_redacted_metrics(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'rates.db')
    with TestClient(app.app) as c:
        for _ in range(30):
            assert c.post('/auth/session').status_code==401
        r=c.post('/auth/session');assert r.status_code==429 and r.headers['retry-after']=='60'
        assert c.get('/integration/v1/metrics/prometheus').status_code==401
        r=c.get('/integration/v1/metrics/prometheus',headers={'X-Internal-Key':app.KEY})
        assert r.status_code==200 and 'gradientzero_http_requests_total' in r.text
        assert 'session_id' not in r.text and app.KEY not in r.text


def test_untrusted_host_rejected(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'host.db')
    with TestClient(app.app) as c:
        assert c.get('/health',headers={'Host':'attacker.invalid'}).status_code==400
