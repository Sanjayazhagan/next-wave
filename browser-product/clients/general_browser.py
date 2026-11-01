"""Core's provider-neutral observe ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ decide externally ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ validate ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ act client."""
import httpx
from clients.reliability import request_with_backoff,not_applied
from browser.protocol import BrowserAction,ContextStart,ModelDecision,ModelPort,validate_decision


class GeneralBrowserClient:
    def __init__(self,base_url,service_key):
        self.pending_actions={}
        self.http=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/integration/v2/browser/',headers={'X-Internal-Key':service_key},timeout=60)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.http.aclose()
    async def request(self,method,path,body=None):
        return await request_with_backoff(self.http,method,path,body)
    async def create(self,request:ContextStart):return await self.request('POST','contexts',request.model_dump())
    async def observe(self,ident):return await self.request('GET',f'contexts/{ident}/observe')
    async def model_input(self,ident,goal):return await self.request('POST',f'contexts/{ident}/model-input',{'goal':goal})
    async def act(self,ident,action:BrowserAction):
        pending=self.pending_actions.get(ident)
        if pending and pending!=action.model_dump():raise RuntimeError('A prior action is unresolved; reconcile or retry_pending with its original ID')
        self.pending_actions[ident]=action.model_dump()
        try:
            result=await self.request('POST',f'contexts/{ident}/actions',action.model_dump())
        except httpx.HTTPStatusError as exc:
            if not_applied(exc.response):self.pending_actions.pop(ident,None)
            raise
        else:
            self.pending_actions.pop(ident,None);return result
    async def retry_pending(self,ident):
        if ident not in self.pending_actions:raise ValueError('No pending action')
        return await self.act(ident,BrowserAction.model_validate(self.pending_actions[ident]))
    async def apply_decision(self,ident,decision,observation):
        parsed=validate_decision(decision,observation)
        if parsed.outcome!='act':return {'paused':True,'decision':parsed.model_dump()}
        return await self.act(ident,parsed.action)
    async def step_with_model(self,ident,goal,model:ModelPort,*,max_replans=2):
        """One explicitly requested tool step for a core graph node, not an agent loop."""
        if model is None:raise ValueError('Core must supply a model adapter; no fallback model/decision is invented')
        if ident in self.pending_actions:raise RuntimeError('Prior action outcome unresolved; reconcile before planning')
        if not 0<=max_replans<=3:raise ValueError('max_replans must be between 0 and 3')
        for attempt in range(max_replans+1):
            payload=await self.model_input(ident,goal)
            obs=payload['observation']
            if obs.get('consent_required'):return {'paused':True,'reason':'citizen_consent_choice_required'}
            if obs.get('needs_reconciliation'):return {'paused':True,'reason':'action_outcome_unknown'}
            if obs.get('page_status','ready')!='ready':
                return {'paused':True,'reason':obs['page_status']}
            decision=await model.decide(request=payload)
            data=decision.model_dump() if isinstance(decision,ModelDecision) else decision
            try:return await self.apply_decision(ident,data,obs)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code!=409 or not not_applied(exc.response) or attempt==max_replans:raise
    async def close(self,ident):return await self.request('DELETE',f'contexts/{ident}')
