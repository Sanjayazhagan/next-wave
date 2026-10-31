"""Package an allowlisted source distribution, excluding all runtime data/secrets."""
import hashlib
import json
from pathlib import Path
import zipfile


def package():
    root=Path(__file__).resolve().parents[1];out=root/'output'/'release';out.mkdir(parents=True,exist_ok=True)
    folders=('browser','server','web','clients','contracts','deploy','docs','scripts','tests','.github')
    names=('README.md','AGENTS.md','requirements.txt','requirements.lock','pyproject.toml','Dockerfile','compose.yaml','compose.vm.yaml','compose.integrated.yaml','.env.example','.env.vm.example','.dockerignore','.gitignore','start-local.cmd')
    files=[]
    for folder in folders:
        for p in (root/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.db','.enc','.log','.zip'):
                files.append(p)
    files.extend(root/n for n in names if (root/n).is_file())
    manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    target=out/'gradientzero-browser-integration.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(manifest):
            info=zipfile.ZipInfo('gradientzero-browser/'+name,date_time=(2026,10,31,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(root/name).read_bytes())
        z.writestr('gradientzero-browser/SOURCE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise RuntimeError('Archive integrity check failed')
        for name in manifest:
            assert hashlib.sha256(z.read('gradientzero-browser/'+name)).hexdigest()==manifest[name]
    (out/'package.json').write_text(json.dumps({'archive':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_files':len(manifest),'runtime_data_included':False},indent=2),encoding='utf-8')
    print('Verified source archive:',target)
    return target


if __name__=='__main__':package()
