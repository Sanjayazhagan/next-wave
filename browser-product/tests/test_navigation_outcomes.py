import json
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from browser.native_submit import reviewed_target
from browser.protocol import BrowserAction


def test_editable_controls_are_not_final_just_because_form_action_is_submit():
    from browser.step_policy import category
    for kind in ['checkbox','radio','text','email']:
        assert category({'tag':'input','type':kind,'label':'Choice','form_action':'https://fixture.test/form/submit'})=='ordinary'
    assert category({'tag':'button','type':'submit','label':'Submit','form_action':'https://fixture.test/form/submit'})=='final'


@pytest.mark.asyncio
async def test_busy_lock_is_a_known_non_applied_error():
    import asyncio
    from browser.general import lock_guard
    lock=asyncio.Lock();await lock.acquire()
    try:
        with pytest.raises(HTTPException) as busy:
            async with lock_guard(lock,timeout=.01):raise AssertionError('must not execute')
        assert busy.value.status_code==409 and busy.value.headers['X-Browser-Outcome']=='not_applied'
    finally:lock.release()


def test_native_submit_requires_exact_reviewed_target_and_complete_form(monkeypatch):
    e={'form':True,'form_method':'get','form_action':'https://www.selenium.dev/selenium/web/submitted-form.html','form_state_complete':True}
    monkeypatch.setenv('BROWSER_FINAL_SUBMIT_TARGETS_JSON','[]')
    with pytest.raises(HTTPException):reviewed_target('https://www.selenium.dev/selenium/web/web-form.html',e)
    monkeypatch.setenv('BROWSER_FINAL_SUBMIT_TARGETS_JSON',json.dumps([{'url':e['form_action'],'method':'GET'}]))
    assert reviewed_target('https://www.selenium.dev/selenium/web/web-form.html',e)[0]=='GET'
    with pytest.raises(HTTPException):reviewed_target('https://other.example/',e)
    with pytest.raises(HTTPException):reviewed_target('https://www.selenium.dev/',{**e,'form_state_complete':False})


@pytest.mark.asyncio
async def test_v2_known_rejection_is_replayed_as_rejection_and_unknown_blocks_new_ids(monkeypatch,tmp_path):
    from server import app,browser_v2
    monkeypatch.setattr(app,'DB',tmp_path/'outcomes.db')
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    with TestClient(app.app):pass
    browser_v2.initialize()
    from server.conversation_bridge import initialize
    initialize()
    with app.conn() as db:
        db.execute('INSERT INTO browser_contexts VALUES(?,?,?,?,?,?,?,?)',('fixture','request-001','hash','citizen','worker-id','generation','active',0))
    calls=[]
    async def reject(*args,**kwargs):
        calls.append(args);raise HTTPException(409,'Observation is stale; observe the page again',headers={'X-Browser-Outcome':'not_applied'})
    monkeypatch.setattr(app,'worker',reject)
    req=BrowserAction(action_id='known-rejected-action',observation_id='old',kind='fill',target_ref='field',value='fixture',verified=True,source_ref='fixture')
    for _ in range(2):
        with pytest.raises(HTTPException) as error:await browser_v2.action('fixture',req,app.KEY)
        assert error.value.status_code==409 and 'Observation is stale' in error.value.detail
    assert len(calls)==1
    with app.conn() as db:
        assert db.execute('SELECT state FROM browser_actions').fetchone()['state']=='rejected'
        assert db.execute('SELECT state FROM browser_contexts').fetchone()['state']=='active'
    async def unknown(*args,**kwargs):raise HTTPException(504,'Browser worker timed out')
    monkeypatch.setattr(app,'worker',unknown)
    with pytest.raises(HTTPException):await browser_v2.action('fixture',req.model_copy(update={'action_id':'unknown-action'}),app.KEY)
    with app.conn() as db:assert db.execute('SELECT state FROM browser_contexts').fetchone()['state']=='needs_reconciliation'
    with pytest.raises(HTTPException) as blocked:await browser_v2.action('fixture',req.model_copy(update={'action_id':'another-action'}),app.KEY)
    assert blocked.value.status_code==409
    async def read(*args,**kwargs):return {'text':'Inspect without replaying'}
    monkeypatch.setattr(app,'worker',read)
    assert (await browser_v2.observation('fixture',app.KEY))['text']=='Inspect without replaying'
