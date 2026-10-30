"""Unpack the actual source archive, install its lockfile in a fresh venv, run HTTP E2E."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.package_release import package


def main():
    root=Path(__file__).resolve().parents[1];out=root/'output'/'release';archive=package()
    uv=shutil.which('uv')
    if not uv:raise RuntimeError('uv is required to verify a fresh lockfile install')
    env=dict(os.environ,UV_CACHE_DIR=str(root/'.uv-cache'),PYTHONUTF8='1',PYTHONPATH='',APP_MODE='demo',SECURITY_MODE='local-demo')
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp).resolve()
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                destination=(target/item.filename).resolve()
                if not destination.is_relative_to(target):raise ValueError('Unsafe archive path')
            z.extractall(target)
        source=target/'gradientzero-browser'
        assert (source/'web'/'index.html').exists() and (source/'web'/'browser_lab.html').exists()
        assert not (source/'data').exists() and not (source/'.env').exists()
        venv=target/'clean-env';python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        with (out/'clean-install.log').open('w',encoding='utf-8') as log:
            for args in ([uv,'venv','--python',sys._base_executable,str(venv)],
                         [uv,'pip','install','--offline','--python',str(python),'-r',str(source/'requirements.lock')],
                         [str(python),'scripts/verify_handoff.py'],
                         [str(python),'scripts/verify_general_browser.py'],
                         [str(python),'scripts/verify_conversation.py']):
                result=subprocess.run(args,cwd=source,env=env,stdout=log,stderr=log,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if result.returncode:raise RuntimeError('Packaged clean-install check failed; inspect output/release/clean-install.log')
        report={'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'fresh_virtual_environment':True,'pinned_dependencies_installed':True,'source_archive_includes_frontend':True,'packaged_human_handoff_http':'passed','packaged_general_browser_http':'passed','packaged_conversation_transport_http':'passed','runtime_keys_or_data_packaged':False}
        (out/'clean-install.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report)


if __name__=='__main__':main()
