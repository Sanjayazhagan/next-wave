"""Create local secrets without printing them. Never commits generated configuration."""
import argparse
import json
from pathlib import Path
import secrets
from cryptography.fernet import Fernet


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--signed',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];path=root/'data'/'local-config.json';path.parent.mkdir(exist_ok=True)
    config={'DATABASE_PATH':str(root/'data'/'encrypted-demo.db'),'APP_MODE':'demo','SECURITY_MODE':'signed' if args.signed else 'local-demo','INTERNAL_KEY':secrets.token_hex(32),'APP_SIGNING_KEY':secrets.token_hex(32),'IDENTITY_SIGNING_KEY':secrets.token_hex(32),'DATA_ENCRYPTION_KEYS':Fernet.generate_key().decode()}
    with path.open('x',encoding='utf-8') as f:json.dump(config,f,indent=2)
    path.chmod(0o600)
    print('Created data/local-config.json. Keys were not printed. Protect this file and back up its encryption keys separately.')
