"""Async core/remote client. Never automatically retries an uncertain command."""
import httpx
from server.contracts import BrowserStart, BrowserCommand


class BrowserClient:
    def __init__(self, base_url: str, service_key: str):
        self.http = httpx.AsyncClient(base_url=base_url.rstrip('/'), timeout=45,
                                      headers={'X-Internal-Key':service_key})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http.aclose()

    async def request(self, method, path, body=None):
        result = await self.http.request(method, '/integration/v1'+path, json=body)
        result.raise_for_status()
        return result.json()

    async def start(self, request: BrowserStart):
        return await self.request('POST','/sessions',request.model_dump())

    async def command(self, session_id: str, command: BrowserCommand):
        return await self.request('POST',f'/sessions/{session_id}/commands',command.model_dump())

    async def session(self, session_id: str):
        return await self.request('GET',f'/sessions/{session_id}')

    async def events(self, session_id: str, after: int = 0):
        return await self.request('GET',f'/events/{session_id}?after={max(0,after)}')

    async def human_task(self, session_id: str):
        return await self.request('POST','/human-tasks',{'session_id':session_id})

    async def cancel_task(self, task_id: str):
        return await self.request('POST',f'/human-tasks/{task_id}/cancel',{})

    async def upload_artifact(self,session_id: str,document: dict):
        return await self.request('POST',f'/sessions/{session_id}/artifacts',document)

    async def reconcile_task(self,task_id: str):
        return await self.request('POST',f'/human-tasks/{task_id}/reconcile',{})

    async def metrics(self):
        return await self.request('GET','/metrics')
    async def receipt(self,session_id:str):
        r=await self.http.get('/integration/v1/sessions/'+session_id+'/receipt');r.raise_for_status();return r.content
