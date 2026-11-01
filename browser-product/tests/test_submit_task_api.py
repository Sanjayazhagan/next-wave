import asyncio
import time
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from server import app,core_assist as assist
from server.submit_tasks import public_origin

@pytest.fixture
def api_setup(tmp_path,monkeypatch):
    monkeypatch.setattr(app,'DB',tmp_path/'submit-tasks.db');monkeypatch.setattr(app,'audit',lambda *args,**kwargs:None)
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode());monkeypatch.setenv('DEMO_HOST','browser.example.org');monkeypatch.delenv('PUBLIC_BASE_URL',raising=False)
    return monkeypatch

async def offered():
    return await assist.offer('browser-session',assist.Offer(reason='submit',review_observation_id='review-observation',approval_ref='citizen-approval',target_ref='final-target'),None,app.KEY)

def control_request():return assist.Control(kind='click',target_ref='final-target',observation_id='human-view-observation')

@pytest.mark.asyncio
async def test_concurrent_click_single_dispatch_and_encrypted_polled_result(api_setup):
    calls=[];result={'state':'completed','confirmed_by_portal':True,'receipt_number':'PRACTICE-123','page_text':'private receipt text','needs_reconciliation':False}
    async def worker(method,path,payload=None,timeout=20):
        if path.endswith('/human-act'):calls.append(payload);await asyncio.sleep(.02);return result
        return {'state':'paused_for_human'}
    api_setup.setattr(app,'worker',worker)
    task=await offered();assert task['assistance_url'].startswith('https://browser.example.org/core-assist/') and task['single_use']
    assert 590<task['expires_at']-time.time()<=600
    token=task['assistance_path'].split('#')[1]
    responses=await asyncio.gather(assist.control(task['task_id'],control_request(),token),assist.control(task['task_id'],control_request(),token),return_exceptions=True)
    assert len(calls)==1 and sum(isinstance(r,HTTPException) for r in responses)==1
    polled=await assist.status('browser-session',app.KEY)
    assert polled['state']=='completed' and polled['receipt_number']=='PRACTICE-123' and polled['confirmed_by_portal']
    with app.conn() as db:stored=db.execute('SELECT payload FROM core_assist_results').fetchone()['payload']
    assert stored.startswith('encrypted:v1:') and 'private receipt text' not in stored
    with pytest.raises(HTTPException):assist.lookup(task['task_id'],token)
    with pytest.raises(HTTPException):await offered()

@pytest.mark.asyncio
async def test_lost_response_quarantined_and_late_status_reconciles(api_setup):
    calls=[];task_id=None
    async def worker(method,path,payload=None,timeout=20):
        if path.endswith('/human-act'):calls.append(payload);raise HTTPException(504,'response lost')
        if path.endswith('/human-status'):return {'task_id':task_id,'result':{'state':'completed','confirmed_by_portal':True,'receipt_number':'LATE-123','needs_reconciliation':False}}
        return {'state':'paused_for_human'}
    api_setup.setattr(app,'worker',worker)
    task=await offered();task_id=task['task_id'];token=task['assistance_path'].split('#')[1]
    with pytest.raises(HTTPException):await assist.control(task_id,control_request(),token)
    with pytest.raises(HTTPException):await assist.control(task_id,control_request(),token)
    assert len(calls)==1
    polled=await assist.status('browser-session',app.KEY)
    assert polled['state']=='completed' and polled['receipt_number']=='LATE-123'

@pytest.mark.asyncio
async def test_expiry_and_nonclicks_do_not_dispatch_submit(api_setup):
    calls=[]
    async def worker(method,path,payload=None,timeout=20):calls.append(path);return {'state':'paused_for_human'}
    api_setup.setattr(app,'worker',worker)
    task=await offered();token=task['assistance_path'].split('#')[1]
    with pytest.raises(HTTPException):await assist.control(task['task_id'],assist.Control(kind='fill',value='not allowed'),token)
    assert len(calls)==1
    with app.conn() as db:db.execute('UPDATE core_assist_tasks SET expires=?',(time.time()-1,))
    with pytest.raises(HTTPException):await assist.control(task['task_id'],control_request(),token)
    assert len(calls)==1

@pytest.mark.asyncio
async def test_changed_view_revokes_link_and_reports_new_review(api_setup):
    async def worker(method,path,payload=None,timeout=20):
        if path.endswith('/human-view'):raise HTTPException(409,'Review page changed',headers={'X-Browser-Outcome':'not_applied'})
        return {'state':'paused_for_human'}
    api_setup.setattr(app,'worker',worker)
    task=await offered();token=task['assistance_path'].split('#')[1]
    with pytest.raises(HTTPException):await assist.view(task['task_id'],token)
    result=await assist.status('browser-session',app.KEY)
    assert result['state']=='review_changed' and result['needs_new_review'] and not result['click_attempted']
    assert result['reason']=='submit'
    with pytest.raises(HTTPException):assist.lookup(task['task_id'],token)

def test_public_origin_uses_only_configured_https_and_fails_clearly_in_azure(monkeypatch):
    monkeypatch.setenv('APP_MODE','integrated');monkeypatch.delenv('DEMO_HOST',raising=False);monkeypatch.delenv('PUBLIC_BASE_URL',raising=False)
    with pytest.raises(HTTPException) as error:public_origin()
    assert error.value.status_code==503
    monkeypatch.setenv('PUBLIC_BASE_URL','https://browser.example.org')
    assert public_origin()=='https://browser.example.org'
    for value in ['https://attacker@browser.example.org','http://browser.example.org','https://browser.example.org/redirect','https://bad host']:
        monkeypatch.setenv('PUBLIC_BASE_URL',value)
        with pytest.raises(HTTPException):public_origin()

@pytest.mark.asyncio
async def test_completed_practice_submission_without_receipt_polls_durably(api_setup):
    """A successful Selenium-like form has no receipt but is not uncertain."""
    evidence={
        'state':'completed','outcome':'portal_confirmed',
        'confirmation_evidence':'reviewed_confirmation',
        'confirmed_by_portal':True,'receipt_number':None,
        'click_attempted':True,'request_observed':True,'needs_reconciliation':False,
        'url':'https://www.selenium.dev/selenium/web/submitted-form.html',
    }
    async def worker(method,path,payload=None,timeout=20):
        if path.endswith('/human-act'):return evidence
        return {'state':'paused_for_human'}
    api_setup.setattr(app,'worker',worker)
    task=await offered()
    token=task['assistance_path'].split('#')[1]
    result=await assist.control(task['task_id'],control_request(),token)
    assert result==evidence
    polled=await assist.status('browser-session',app.KEY)
    assert polled['state']=='completed' and polled['receipt_number'] is None
    assert polled['outcome']=='portal_confirmed' and polled['confirmation_evidence']=='reviewed_confirmation'
    assert not polled['needs_reconciliation']
    assert 'page_text' not in polled
    with pytest.raises(HTTPException):await assist.control(task['task_id'],control_request(),token)
    assert (await assist.status('browser-session',app.KEY))['state']=='completed'
