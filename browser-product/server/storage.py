"""Authenticated encryption for bounded browser-owned records and artifacts."""
import base64
import json
import os
from cryptography.fernet import Fernet, MultiFernet

PREFIX = 'encrypted:v1:'


def cipher():
    keys = [k.strip() for k in os.getenv('DATA_ENCRYPTION_KEYS','').split(',') if k.strip()]
    if not keys:
        raise RuntimeError('DATA_ENCRYPTION_KEYS is required for encrypted storage')
    return MultiFernet([Fernet(k.encode()) for k in keys])


def pack(raw: bytes, scope: str) -> bytes:
    envelope = json.dumps({'scope':scope,'data':base64.b64encode(raw).decode()},separators=(',',':')).encode()
    return cipher().encrypt(envelope)


def unpack(token: bytes, scope: str) -> bytes:
    envelope = json.loads(cipher().decrypt(token))
    if envelope.get('scope') != scope:
        raise ValueError('Encrypted record scope mismatch')
    return base64.b64decode(envelope['data'],validate=True)


def seal(value: str, scope: str) -> str:
    if not os.getenv('DATA_ENCRYPTION_KEYS'):
        if os.getenv('SECURITY_MODE') == 'signed':
            raise RuntimeError('Signed mode refuses plaintext sensitive records')
        return value  # Explicit local synthetic compatibility mode only.
    return PREFIX+pack(value.encode(),scope).decode()


def unseal(value: str, scope: str) -> str:
    if value.startswith(PREFIX):
        return unpack(value[len(PREFIX):].encode(),scope).decode()
    if os.getenv('SECURITY_MODE') == 'signed':
        raise RuntimeError('Plaintext legacy record must be migrated before signed mode')
    return value


def rotate(value: str) -> str:
    if not value.startswith(PREFIX):
        raise ValueError('Only encrypted records can be rotated')
    return PREFIX+cipher().rotate(value[len(PREFIX):].encode()).decode()
