from fastapi.testclient import TestClient
from server.app import app
from browser.core_compat import BridgeSession,receipt_from_observation
from server.practice_scholarship import RECEIPT_PATTERN

def values():return {'name':'Demo Student','email':'demo@example.invalid','age':'20','income':'50000','course':'degree','synthetic':'yes'}

def test_practice_form_receipt_is_real_and_contains_no_applicant_details():
    with TestClient(app) as c:
        page=c.get('/practice/scholarship');assert page.status_code==200 and 'Mock scholarship application' in page.text and 'Practice only' in page.text
        result=c.post('/practice/scholarship/submit',data=values())
        assert result.status_code==200 and 'Application successfully submitted' in result.text
        assert 'Demo Student' not in result.text and 'demo@example.invalid' not in result.text
        receipt=receipt_from_observation({'text':result.text},BridgeSession('fixture','scholarship_practice',receipt_pattern=RECEIPT_PATTERN))
        assert receipt and receipt.startswith('DEMO-SCH-')
        forged=receipt[:-1]+('A' if receipt[-1]!='A' else 'B')
        assert c.get('/practice/scholarship/receipt/'+forged).status_code==404

def test_practice_rejects_invalid_form_and_never_echoes_inputs():
    with TestClient(app) as c:
        for change in ({'synthetic':'no'},{'income':'not numeric'},{'age':'2'},{'course':'other'},{'name':'<script>secret</script>','email':'invalid'}):
            r=c.post('/practice/scholarship/submit',data={**values(),**change});assert r.status_code==422 and '<script>secret' not in r.text
        assert c.post('/practice/scholarship/submit',json=values()).status_code==415

def test_practice_is_available_in_signed_mode_but_core_is_not_public(monkeypatch):
    from server import app as application
    monkeypatch.setenv('SECURITY_MODE','signed');monkeypatch.setattr(application,'MODE','integrated')
    # Only the explicit synthetic practice routes skip identity; service endpoints do not.
    from starlette.requests import Request
    from server.security import enforce
    scope={'type':'http','method':'GET','scheme':'https','server':('browser.example',443),'headers':[],'query_string':b'','path':'/practice/scholarship'}
    assert enforce(Request(scope)) is None
    c=TestClient(app)
    assert c.get('/practice/scholarship').status_code==200
    assert c.post('/core-browser/session',json={'portal_id':'scholarship_practice'}).status_code==401
