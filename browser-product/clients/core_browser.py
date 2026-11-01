"""One caller-requested bridge step; core supplies decisions and citizen replies."""
import httpx
import uuid
from clients.reliability import request_with_backoff,not_applied

class CoreBrowserClient:
    def __init__(self, base_url, service_key, *, transport=None):
        self.pending_actions={}
        self.http=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/core-browser/',
            headers={'X-Internal-Key':service_key},timeout=60,transport=transport)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.http.aclose()
    async def request(self,method,path,body=None):
        return await request_with_backoff(self.http,method,path,body)
    async def open_url(self,url,consent_ref):
        if not url or not consent_ref:raise ValueError('Explicit URL and citizen consent required')
        return await self.request('POST','session',{'url':url,'consent_ref':consent_ref})
    async def snapshot(self,sid):return await self.request('GET',f'session/{sid}/snapshot')
    async def human_task(self,sid,reason,*,review_observation_id=None,approval_ref=None,target_ref=None,ttl_seconds=None):
        options={'review_observation_id':review_observation_id,'approval_ref':approval_ref,'target_ref':target_ref,'ttl_seconds':ttl_seconds}
        return await self.request('POST',f'session/{sid}/human-task',{'reason':reason,**{k:v for k,v in options.items() if v is not None}})
    async def human_task_status(self,sid):return await self.request('GET',f'session/{sid}/human-task')
    async def close(self,sid):return await self.request('DELETE',f'session/{sid}')
    async def retry_pending(self,sid):
        if sid not in self.pending_actions:raise ValueError('No pending action')
        result=await self.request('POST',f'session/{sid}/action',self.pending_actions[sid])
        self.pending_actions.pop(sid,None)
        return result
    async def step(self,sid,decide,*,max_replans=2):
        """Re-decide only after known pre-action staleness, never replay a write.

        Do not retry network errors, missing files, human-ownership conflicts,
        expired approvals or other uncertain outcomes. No LLM is bundled.
        """
        if sid in self.pending_actions:raise RuntimeError('A prior action outcome is unresolved; inspect and use retry_pending with its original ID')
        if not 0<=max_replans<=3:raise ValueError('max_replans must be between 0 and 3')
        for attempt in range(max_replans+1):
            snapshot=await self.snapshot(sid)
            if snapshot.get('consent_required'):return {'paused':True,'reason':'citizen_consent_choice_required','human_signals':snapshot.get('human_signals',[])}
            if snapshot.get('session_expired'):return {'paused':True,'reason':'session_expired','requires_reauthentication':True}
            if snapshot.get('needs_reconciliation'):return {'paused':True,'reason':'action_outcome_unknown'}
            if snapshot.get('page_status','ready')!='ready':
                return {'paused':True,'reason':snapshot['page_status'],'human_signals':snapshot.get('human_signals',[])}
            if snapshot.get('challenge'):
                return {'paused':True,'reason':'human_verification','challenge':snapshot['challenge']}
            action=await decide(snapshot)
            if action is None:return {'paused':True,'reason':'core_requested_pause'}
            action={**action,'action_id':action.get('action_id') or str(uuid.uuid4())}
            self.pending_actions[sid]=action
            try:
                result=await self.request('POST',f'session/{sid}/action',action)
                self.pending_actions.pop(sid,None)
                return result
            except httpx.HTTPStatusError as exc:
                try:detail=exc.response.json().get('detail','')
                except ValueError:detail=''
                stale=not_applied(exc.response) and any(text in str(detail) for text in ('Page changed since','Target no longer observed','Target changed;','not currently actionable'))
                if stale or exc.response.headers.get('X-Browser-Outcome')=='not_applied' or exc.response.status_code in (400,401,403,422,429):self.pending_actions.pop(sid,None)
                if exc.response.status_code!=409 or not stale or attempt==max_replans:raise
