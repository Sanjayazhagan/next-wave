"""Start both local ASGI services; no Docker, Node, cloud or paid keys required."""
import os, subprocess, sys, signal, time, json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
os.chdir(root)
env=os.environ.copy()
config=root/'data'/'local-config.json'
if config.exists():
 for name,value in json.loads(config.read_text(encoding='utf-8')).items():
  env.setdefault(name,str(value))
env.setdefault('APP_MODE','demo')
api_port=os.getenv('API_PORT','8100')
worker_port=os.getenv('WORKER_PORT','8101')
env.setdefault('MOCK_BASE_URL','http://127.0.0.1:'+api_port)
env.setdefault('WORKER_URL','http://127.0.0.1:'+worker_port)
env.setdefault('CHROMIUM_PATH','/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else '')
processes=[]
try:
 for module,port in [('browser.worker:app',worker_port),('server.app:app',api_port)]:
  processes.append(subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',port],env=env))
 print(f'GradientZero demo: http://127.0.0.1:{api_port}   /docs for API. Ctrl+C to stop.',flush=True)
 while all(p.poll() is None for p in processes): time.sleep(.3)
finally:
 for p in processes:
  if p.poll() is None:p.terminate()
 for p in processes:
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill()
