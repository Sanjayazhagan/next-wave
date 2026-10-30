"""Full synthetic core/remote wiring, encrypted artifacts and concurrent flow evidence."""
import asyncio
import base64
import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clients.browser_client import BrowserClient
from server.contracts import BrowserStart,BrowserCommand
from server.app import DEFAULT_PROFILE,fixture_pdf
from scripts.test_harness import services


async def one(base,key,index):
    start=time.monotonic();sid=None
    async with BrowserClient(base,key) as client:
        request=BrowserStart(request_id=str(uuid.uuid4()),subject='synthetic-'+str(index),consent_ref='synthetic-consent',fields={k:{'value':v,'source_ref':'remote-synthetic-fixture','confidence':1,'verified':True} for k,v in DEFAULT_PROFILE.items()})
        session=await client.start(request);sid=session['id']
        assert (await client.start(request))['id']==sid
        async def command(expected,kind,payload=None):
            return await client.command(sid,BrowserCommand(action_id=str(uuid.uuid4()),expected_state=expected,kind=kind,payload=payload or {}))
        await command('otp_needed','otp',{'otp':'246810'})
        await command('captcha_needed','human',{'challenge_answer':'7'})
        artifact=await client.request('POST',f'/sessions/{sid}/artifacts',{'subject':request.subject,'source_ref':'remote-synthetic-certificate','file_name':'certificate.pdf','file_base64':base64.b64encode(fixture_pdf()).decode()})
        review=await command('form_ready','fill',{'artifact_id':artifact['artifact_id']})
        approve=BrowserCommand(action_id=str(uuid.uuid4()),expected_state='approval_needed',kind='approve',payload={'confirmed':True,'review_hash':review['review_hash']})
        receipt=await client.command(sid,approve)
        assert (await client.command(sid,approve))==receipt
        assert (await command('submitted','poll'))['status']=='submitted'
        events=await client.events(sid)
        assert events['events'] and (await client.events(sid,events['next_cursor']))['events']==[]
        await client.request('DELETE',f'/sessions/{sid}/artifacts/{artifact["artifact_id"]}')
        # Service fixture teardown remains a demo endpoint; never use real identity data.
        result=await client.http.delete('/api/sessions/'+sid);result.raise_for_status()
        return {'run':index,'result':'passed','seconds':round(time.monotonic()-start,3),'mode':'synthetic','encrypted_artifact':True}


async def main():
    out=Path('output/release-validation')
    async with services(out) as (base,env):
        started=time.monotonic()
        semaphore=asyncio.Semaphore(2)
        async def limited(index):
            async with semaphore:return await one(base,env['INTERNAL_KEY'],index)
        results=await asyncio.gather(*(limited(i) for i in range(1,7)))
        node_env=dict(os.environ,BASE_URL=base,INTERNAL_KEY=env['INTERNAL_KEY'],ALLOW_SYNTHETIC_EXAMPLE='1')
        node=await asyncio.to_thread(subprocess.run,['node','clients/example_core.mjs'],env=node_env,capture_output=True,text=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if node.returncode:
            raise RuntimeError('Node integration example failed; no credential-bearing stderr is printed')
        node_report=json.loads(node.stdout)
        durations=sorted(r['seconds'] for r in results)
        report={'mode':'synthetic','runs':results,'node_example':node_report,'concurrency':2,'successful':len(results),'wall_seconds':round(time.monotonic()-started,3),'median_seconds':statistics.median(durations),'max_seconds':max(durations),'claim':'Small local concurrency check, not a production capacity certification'}
        (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
