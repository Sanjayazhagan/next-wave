"""One caller-requested bridge step; core supplies decisions and citizen replies."""
import httpx

class CoreBrowserClient:
    def __init__(self, base_url, service_key, *, transport=None):
        self.http=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/core-browser/',
            headers={'X-Internal-Key':service_key},timeout=45,transport=transport)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.http.aclose()
    async def request(self,method,path,body=None):
        response=await self.http.request(method,path,json=body)
        response.raise_for_status()
        return response.json()
    async def open_url(self,url,consent_ref):
        if not url or not consent_ref:raise ValueError('Explicit URL and citizen consent required')
        return await self.request('POST','session',{'url':url,'consent_ref':consent_ref})
    async def snapshot(self,sid):return await self.request('GET',f'session/{sid}/snapshot')
    async def human_task(self,sid,reason):return await self.request('POST',f'session/{sid}/human-task',{'reason':reason})
    async def close(self,sid):return await self.request('DELETE',f'session/{sid}')
    async def step(self,sid,decide,*,max_replans=2):
        """Re-decide only after known pre-action staleness, never replay a write.

        Do not retry network errors, missing files, human-ownership conflicts,
        expired approvals or other uncertain outcomes. No LLM is bundled.
        """
        if not 0<=max_replans<=3:raise ValueError('max_replans must be between 0 and 3')
        for attempt in range(max_replans+1):
            snapshot=await self.snapshot(sid)
            if snapshot.get('challenge'):
                return {'paused':True,'reason':'human_verification','challenge':snapshot['challenge']}
            action=await decide(snapshot)
            if action is None:return {'paused':True,'reason':'core_requested_pause'}
            try:return await self.request('POST',f'session/{sid}/action',action)
            except httpx.HTTPStatusError as exc:
                try:detail=exc.response.json().get('detail','')
                except ValueError:detail=''
                stale=any(text in str(detail) for text in ('Page changed since','Target no longer observed','Target changed;'))
                if exc.response.status_code!=409 or not stale or attempt==max_replans:raise
