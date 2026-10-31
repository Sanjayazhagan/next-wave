import httpx
import pytest
from clients.core_browser import CoreBrowserClient

@pytest.mark.asyncio
async def test_stale_step_observes_and_redecides():
    counts={'snapshots':0,'actions':0};decisions=[]
    def handler(req):
        if req.method=='GET':
            counts['snapshots']+=1
            return httpx.Response(200,json={'observation_id':str(counts['snapshots'])})
        counts['actions']+=1
        if counts['actions']==1:return httpx.Response(409,json={'detail':'Page changed since the core snapshot; reobserve and replan'})
        return httpx.Response(200,json={'ok':True})
    async def decide(s):decisions.append(s['observation_id']);return {'type':'click'}
    async with CoreBrowserClient('http://local','test',transport=httpx.MockTransport(handler)) as client:
        assert (await client.step('sid',decide))['ok']
    assert decisions==['1','2'] and counts['actions']==2

@pytest.mark.asyncio
async def test_unknown_outcome_is_never_retried():
    calls=[]
    def handler(req):
        if req.method=='GET':return httpx.Response(200,json={})
        calls.append(req);raise httpx.ReadTimeout('unknown action outcome',request=req)
    async def decide(s):return {'type':'click'}
    async with CoreBrowserClient('http://local','test',transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):await client.step('sid',decide)
    assert len(calls)==1

@pytest.mark.asyncio
async def test_numeric_otp_challenge_pauses_before_planner():
    def handler(req):return httpx.Response(200,json={'challenge':{'kind':'otp','input':{'role':'spinbutton','name':'OTP Code'}}})
    async def decide(s):raise AssertionError('OTP must be handled before ordinary planning')
    async with CoreBrowserClient('http://local','test',transport=httpx.MockTransport(handler)) as client:
        result=await client.step('sid',decide)
    assert result['paused'] and result['challenge']['kind']=='otp'
