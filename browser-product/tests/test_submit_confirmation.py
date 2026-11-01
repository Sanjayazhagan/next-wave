"""Submission confirmation requires portal-reviewed evidence, never URL-only guessing."""
import json
import pytest
from fastapi import HTTPException
from browser.submit_confirmation import confirmation_evidence, reviewed_rules

SOURCE = 'https://www.selenium.dev/selenium/web/web-form.html'
SUCCESS = 'https://www.selenium.dev/selenium/web/submitted-form.html'


def observed(url=SUCCESS, text='Form submitted\nReceived!', page_status='ready'):
    return {'url': url, 'text': text, 'page_status': page_status}


def decide(source=SOURCE, after=None, *, requested=True, changed=True, receipt=None):
    return confirmation_evidence(source, after or observed(), request_observed=requested, changed=changed, receipt=receipt)


def test_selenium_success_without_receipt_is_explicitly_confirmed(monkeypatch):
    monkeypatch.delenv('BROWSER_SUBMIT_CONFIRMATIONS_JSON', raising=False)
    assert decide() == 'reviewed_confirmation'


@pytest.mark.parametrize('changes', [
    {'source': 'https://www.selenium.dev/selenium/web/other.html'},
    {'url': 'https://www.selenium.dev/selenium/web/web-form.html'},
    {'url': 'https://www.selenium.dev/selenium/web/submitted-form.html?spoof=1'},
    {'text': 'Form submitted but not Received'},
    {'text': 'Received! (but no form confirmation)'},
    {'page_status': 'blocked'},
    {'requested': False},
    {'changed': False},
])
def test_no_false_confirmation_on_partial_or_unknown_evidence(changes):
    params={'source': SOURCE, 'after': observed(), 'requested': True, 'changed': True}
    for key, value in changes.items():
        if key in ('source', 'requested', 'changed'):
            params[key] = value
        else:
            params['after'] = {**params['after'], key: value}
    assert decide(**params) is None


def test_explicit_receipt_pattern_remains_supported():
    assert decide(source='https://some.gov.example/form', after=observed(url='https://some.gov.example/receipt', text='Application successfully submitted Receipt: TEST-1'), receipt='TEST-1') == 'reviewed_receipt'


def test_receipt_alone_does_not_confirm_without_request_or_dom_change():
    assert decide(requested=False, receipt='TEST-1') is None
    assert decide(changed=False, receipt='TEST-1') is None


def test_registered_evidence_succeeds_only_with_full_match(monkeypatch):
    record = {'source_url':'https://practice.example.org/apply', 'success_url':'https://practice.example.org/complete', 'required_text':['Application received', 'Confirmed']}
    monkeypatch.setenv('BROWSER_SUBMIT_CONFIRMATIONS_JSON',json.dumps([record]))
    success = observed(url=record['success_url'],text='Your application received today. Confirmed!')
    assert decide(source=record['source_url'],after=success)=='reviewed_confirmation'
    assert decide(source='https://practice.example.org/other',after=success) is None
    assert decide(source=record['source_url'],after={**success,'text':'Almost complete'}) is None


@pytest.mark.parametrize('registry',[
    '{broken', '{}', '[{}]',
    json.dumps([{'source_url':'http://127.0.0.1:9000/form','success_url':'http://127.0.0.1:9000/ok','required_text':['Confirmed']}]),
    json.dumps([{'source_url':'https://portal.example.org/form','success_url':'https://evil.example.org/ok','required_text':['Confirmed']}]),
    json.dumps([{'source_url':'https://portal.example.org/form','success_url':'https://portal.example.org/ok','required_text':['yes']}]),
    json.dumps([{'source_url':'https://portal.example.org/form','success_url':'https://portal.example.org/ok','required_text':['Confirmed'],'unexpected':'ignored'}]),
])
def test_integrated_mode_bad_operator_rules_fail_closed(monkeypatch,registry):
    monkeypatch.setenv('APP_MODE','integrated')
    monkeypatch.setenv('SECURITY_MODE','signed')
    monkeypatch.setenv('BROWSER_SUBMIT_CONFIRMATIONS_JSON', registry)
    with pytest.raises(HTTPException) as exc:reviewed_rules()
    assert exc.value.status_code==503


def test_local_http_practice_rule_only_when_demo(monkeypatch):
    rule={'source_url':'http://127.0.0.1:9876/start','success_url':'http://127.0.0.1:9876/receipt','required_text':['Received!']}
    monkeypatch.setenv('APP_MODE','demo');monkeypatch.setenv('SECURITY_MODE','local-demo')
    monkeypatch.setenv('BROWSER_SUBMIT_CONFIRMATIONS_JSON',json.dumps([rule]))
    assert decide(source=rule['source_url'],after=observed(url=rule['success_url'],text='Received!'))=='reviewed_confirmation'
