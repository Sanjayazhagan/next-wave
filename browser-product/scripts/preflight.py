import importlib, os, shutil, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
required=['fastapi','uvicorn','httpx','playwright','reportlab','pytest','pydantic']
errors=[]
for mod in required:
    try: importlib.import_module(mod)
    except ImportError:errors.append(f'Missing Python module: {mod}')
try:
    import playwright
    import importlib.metadata
    version=importlib.metadata.version('playwright')
    print('Playwright package:',version)
except Exception: pass
if not shutil.which('chromium'):
    print('Chromium not found on PATH. Use docker compose or install Playwright Chromium.')
else: print('Chromium:',shutil.which('chromium'))
for path in ['server/app.py','browser/worker.py','web/index.html','web/app.js','web/mock.html','docs/MASTER_HANDOFF.md']:
    if not (root/path).exists(): errors.append('Missing file: '+path)
print('Preflight:', 'FAIL' if errors else 'PASS')
for err in errors:print('-',err)
if errors:sys.exit(1)
