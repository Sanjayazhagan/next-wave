"""Actual API/worker process restart test using the versioned core boundary."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import httpx


async def main():
    root = Path(__file__).resolve().parents[1]
    out = root/'output'/'resilience'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, (out/'services.log').open('w',encoding='utf-8') as log:
        env = dict(os.environ, APP_MODE='demo', SECURITY_MODE='local-demo', MOCK_BASE_URL='http://127.0.0.1:8500', WORKER_URL='http://127.0.0.1:8501', DATABASE_PATH=str(Path(tmp)/'state.db'))
        processes = {}
        def launch(name, module, port):
            processes[name] = subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',port], cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def stop(name):
            p = processes.pop(name)
            if os.name == 'nt':
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                p.terminate()
            p.wait(timeout=10)
        async def wait(url):
            async with httpx.AsyncClient() as h:
                for _ in range(100):
                    try:
                        if (await h.get(url,timeout=1)).is_success:
                            return
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.2)
                raise RuntimeError('Test service failed to become ready')
        try:
            launch('worker','browser.worker:app','8501')
            launch('api','server.app:app','8500')
            await wait('http://127.0.0.1:8500/ready')
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8500',headers={'X-Internal-Key':env.get('INTERNAL_KEY','demo-worker-key-change-before-production')},timeout=45) as c:
                async def post(path,data):
                    r=await c.post('/integration/v1'+path,json=data)
                    r.raise_for_status()
                    return r.json()
                from server.app import DEFAULT_PROFILE
                request={'request_id':'restart-request-01','subject':'synthetic-citizen','consent_ref':'synthetic-consent','fields':{k:{'value':v,'source_ref':'synthetic-profile','confidence':1,'verified':True} for k,v in DEFAULT_PROFILE.items()}}
                first=await post('/sessions',request)
                sid=first['id']
                async def cmd(action,expected,kind,payload=None):
                    return await post('/sessions/'+sid+'/commands',{'action_id':action,'expected_state':expected,'kind':kind,'payload':payload or {}})
                stop('worker')
                launch('worker','browser.worker:app','8501')
                await wait('http://127.0.0.1:8501/ready')
                recovered=await cmd('recover-worker-01','otp_needed','resume')
                assert recovered['state']=='otp_needed'
                stop('api')
                launch('api','server.app:app','8500')
                await wait('http://127.0.0.1:8500/ready')
                assert (await post('/sessions',request))['id']==sid
                await cmd('login-code-01','otp_needed','otp',{'otp':'246810'})
                await cmd('human-answer-01','captcha_needed','human',{'challenge_answer':'7'})
                review=await cmd('prepare-form-01','form_ready','fill')
                receipt=await cmd('approval-final-01','approval_needed','approve',{'confirmed':True,'review_hash':review['review_hash']})
                stop('api')
                launch('api','server.app:app','8500')
                await wait('http://127.0.0.1:8500/ready')
                again=await cmd('approval-final-01','approval_needed','approve',{'confirmed':True,'review_hash':review['review_hash']})
                assert again['receipt_id']==receipt['receipt_id']
                status=await cmd('status-check-01','submitted','poll')
                assert status['status']=='submitted'
                report={'mode':'demo','actual_worker_restart':'passed','actual_api_restart_before_login':'passed','actual_api_restart_after_submission':'passed','durable_command_replay_same_receipt':'passed','real_application_submitted':False}
                (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                print('PASS: actual worker/API restarts, fresh human login and durable approval replay without duplicate mock receipt')
        finally:
            for name in list(processes):
                stop(name)


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    asyncio.run(main())
