"""Core's provider-neutral observe → decide externally → validate → act client."""
import httpx
from browser.protocol import BrowserAction,ContextStart,ModelDecision,ModelPort,validate_decision


class GeneralBrowserClient:
    def __init__(self,base_url,service_key):
        self.http=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/integration/v2/browser/',headers={'X-Internal-Key':service_key},timeout=45)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.http.aclose()
    async def request(self,method,path,body=None):
        r=await self.http.request(method,path,json=body);r.raise_for_status();return r.json()
    async def create(self,request:ContextStart):return await self.request('POST','contexts',request.model_dump())
    async def observe(self,ident):return await self.request('GET',f'contexts/{ident}/observe')
    async def model_input(self,ident,goal):return await self.request('POST',f'contexts/{ident}/model-input',{'goal':goal})
    async def act(self,ident,action:BrowserAction):return await self.request('POST',f'contexts/{ident}/actions',action.model_dump())
    async def apply_decision(self,ident,decision,observation):
        parsed=validate_decision(decision,observation)
        if parsed.outcome!='act':return {'paused':True,'decision':parsed.model_dump()}
        return await self.act(ident,parsed.action)
    async def step_with_model(self,ident,goal,model:ModelPort):
        """One explicitly requested tool step for a core graph node, not an agent loop."""
        if model is None:raise ValueError('Core must supply a model adapter; no fallback model/decision is invented')
        payload=await self.model_input(ident,goal)
        decision=await model.decide(request=payload)
        data=decision.model_dump() if isinstance(decision,ModelDecision) else decision
        return await self.apply_decision(ident,data,payload['observation'])
    async def close(self,ident):return await self.request('DELETE',f'contexts/{ident}')
