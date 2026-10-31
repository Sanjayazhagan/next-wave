"""Gateway never exposes the private worker without service authentication."""
import pytest
from fastapi import HTTPException
from server import core_gateway
from server import app

@pytest.mark.asyncio
async def test_core_gateway_requires_internal_key(monkeypatch):
    called=[]
    async def fake_worker(method,path,payload=None,timeout=0):
        called.append((method,path,payload))
        return {'session_id':'isolation-test'}
    monkeypatch.setattr(app,'worker',fake_worker)
    with pytest.raises(HTTPException) as error:
        await core_gateway.open_session(core_gateway.Payload.model_validate({'portal_id':'local'}), None)
    assert error.value.status_code==401
    assert not called
    result=await core_gateway.open_session(core_gateway.Payload.model_validate({'portal_id':'local'}),app.KEY)
    assert result['session_id']=='isolation-test'
    assert called==[('POST','/core/session',{'portal_id':'local'})]

@pytest.mark.asyncio
async def test_gateway_submit_approval_stays_on_private_worker(monkeypatch):
    calls=[]
    async def fake_worker(method,path,payload=None,timeout=0):
        calls.append((method,path,payload))
        return {'authorized':True}
    monkeypatch.setattr(app,'worker',fake_worker)
    await core_gateway.authorize('sid',core_gateway.Payload.model_validate({'approved':True,'approval_ref':'core-session','review_observation_id':'review-1'}),app.KEY)
    assert calls == [('POST','/core/session/sid/authorize-submit',{'approved':True,'approval_ref':'core-session','review_observation_id':'review-1'})]
