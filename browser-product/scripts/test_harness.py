"""Isolated synthetic service harness used by release and benchmark checks."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import httpx
from cryptography.fernet import Fernet


@asynccontextmanager
async def services(out:Path,api_port=8800,worker_port=8801):
    root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp,(out/'services.log').open('w',encoding='utf-8') as log:
        env=dict(os.environ,APP_MODE='demo',SECURITY_MODE='local-demo',INTERNAL_KEY=secrets.token_hex(32),APP_SIGNING_KEY=secrets.token_hex(32),DATA_ENCRYPTION_KEYS=Fernet.generate_key().decode(),MOCK_BASE_URL=f'http://127.0.0.1:{api_port}',WORKER_URL=f'http://127.0.0.1:{worker_port}',DATABASE_PATH=str(Path(tmp)/'test.db'))
        procs=[]
        try:
            for module,port in [('server.app:app',api_port),('browser.worker:app',worker_port)]:
                procs.append(subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            async with httpx.AsyncClient() as c:
                for _ in range(100):
                    if any(p.poll() is not None for p in procs):raise RuntimeError('A test service exited; inspect services.log')
                    try:
                        if (await c.get(f'http://127.0.0.1:{api_port}/ready',timeout=1)).is_success:break
                    except httpx.HTTPError:pass
                    await asyncio.sleep(.2)
                else:raise RuntimeError('Test services did not become ready')
            yield f'http://127.0.0.1:{api_port}',env
        finally:
            for p in procs:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                else:p.terminate()
            for p in procs:
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:p.kill();p.wait()
