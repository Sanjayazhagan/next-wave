"""Temporary real-browser assistance tokens cannot escape their session scope."""
import time
import pytest
from fastapi import HTTPException
from server import app as application
from server import core_assist

@pytest.mark.asyncio
async def test_scoped_link_and_expiration(tmp_path,monkeypatch):
    monkeypatch.setattr(application,'DB',tmp_path/'assist.sqlite')
    monkeypatch.setenv('DEMO_HOST','example.org')
    monkeypatch.setattr(application,'audit',lambda *args,**kwargs:None)
    called=[]
    async def fake_worker(method,path,payload=None,timeout=20):
        called.append((method,path,payload))
        return {'state':'paused_for_human'}
    monkeypatch.setattr(application,'worker',fake_worker)
    res=await core_assist.offer('browser-session-A',core_assist.Offer(reason='otp',ttl_seconds=60),None,application.KEY)
    task=res['task_id'];token=res['assistance_path'].split('#')[1]
    assert 'https://example.org/core-assist/' in res['assistance_url']
    assert core_assist.lookup(task,token)['session_id']=='browser-session-A'
    with pytest.raises(HTTPException):core_assist.lookup(task,'wrong-token')
    with pytest.raises(HTTPException) as duplicate:
        await core_assist.offer('browser-session-A',core_assist.Offer(reason='otp',ttl_seconds=60),None,application.KEY)
    assert duplicate.value.status_code==409
    completed=await core_assist.complete(task,token)
    assert completed['state']=='paused_for_human'
    with pytest.raises(HTTPException):core_assist.lookup(task,token)
    assert len(called)==2
