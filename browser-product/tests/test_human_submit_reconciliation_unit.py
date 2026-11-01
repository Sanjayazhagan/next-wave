"""Exercise the actual human-click status transition without external Chromium."""
import time
from types import SimpleNamespace
import pytest
from browser import human_submit
from browser.core_compat import HumanAction
SOURCE = 'https://www.selenium.dev/selenium/web/web-form.html'
SUCCESS = 'https://www.selenium.dev/selenium/web/submitted-form.html'


@pytest.mark.asyncio
@pytest.mark.parametrize('destination,text,requested,expected', [
    (SUCCESS,'Form submitted\nReceived!',True,'completed'),
    (SUCCESS,'Form submitted\nReceived!',False,'uncertain'),
    (SUCCESS,'Still loading',True,'uncertain'),
    (SOURCE,'Form submitted\nReceived!',True,'uncertain'),
])
async def test_human_click_uses_reviewed_evidence_and_no_fake_receipt(monkeypatch,destination,text,requested,expected):
    task='practice-task-12345'
    info=SimpleNamespace(
        submit_review={'url': SOURCE,'fingerprint':'before','target_ref':'submit-1','scope':('GET','https://www.selenium.dev:443','/selenium/web/submitted-form.html')},
        human_task_id=task,human_expires=time.time()+60,human_result=None,human_result_task_id=None,
        uncertain_action=None,consumed=False,auth_value_entered=False,auth_ref=None,receipt_pattern=None,
    )
    class Page:
        async def wait_for_load_state(self,*args,**kwargs):return None
    ctx=SimpleNamespace(observation_id='human-observation',fingerprint='before',page=Page(),human_captcha_until=0,human_lease_until=time.time()+60)
    async def review(*args):return ({'ref':'submit-1','category':'final'}, {'submit-1':object()})
    class Locator:
        async def click(self,**kwargs):return None
    async def resolve_locator(*args):return Locator()
    async def requested_click(*args):return requested
    async def observe(*args,**kwargs):
        ctx.fingerprint='after'
        return {'url':destination,'text':text,'page_status':'ready','observation_id':'obs-after','elements':[]}
    monkeypatch.setattr(human_submit,'check_review',review)
    monkeypatch.setattr(human_submit,'resolve_target',resolve_locator)
    monkeypatch.setattr(human_submit,'click_reviewed_submit',requested_click)
    monkeypatch.setattr(human_submit,'observe',observe)
    monkeypatch.setattr('browser.core_compat.ensure_human',lambda *args:None)
    monkeypatch.setattr('browser.core_compat.convert',lambda *args:None)
    monkeypatch.setattr('browser.core_compat.receipt_from_observation',lambda *args:None)
    req=HumanAction(task_id=task,kind='click',observation_id='human-observation',target_ref='submit-1')
    result=await human_submit.click(info,ctx,req)
    assert result['state']==expected
    assert result['confirmed_by_portal']==(expected=='completed')
    assert result['receipt_number'] is None
    assert result['click_attempted']
    assert result['needs_reconciliation']==(expected=='uncertain')
    assert 'page_text' not in result
    assert info.consumed
    assert info.human_result==result and info.human_result_task_id==task
    assert info.human_task_id is None
    assert (info.uncertain_action is None)==(expected=='completed')
