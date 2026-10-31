"""Core-issued, audience-scoped identity assertions; optional secured local mode.

This is an integration boundary, not a user directory or identity provider.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import urlsplit
from fastapi import HTTPException


def encode(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def mint(subject, role, key, ttl=300):
    if role not in ('citizen', 'operator', 'core') or not subject or not 1 <= ttl <= 900:
        raise ValueError('Invalid identity assertion')
    payload = encode(json.dumps({'sub': subject, 'role': role, 'aud': 'gradientzero-browser', 'exp': time.time()+ttl, 'iat':time.time(), 'jti':str(uuid.uuid4())}, separators=(',', ':')).encode())
    return payload+'.'+encode(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest())


def verify(token, key):
    try:
        payload, signature = token.split('.')
        expected = encode(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if data['aud'] != 'gradientzero-browser' or data['role'] not in ('citizen','operator','core') or not isinstance(data['sub'], str) or not data['sub'] or not time.time() < data['exp'] <= time.time()+900:
            raise ValueError()
        if not isinstance(data.get('iat'), (int,float)) or data['iat']>time.time()+1 or data['exp']-data['iat']>901 or not isinstance(data.get('jti'),str):
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(401, 'Invalid or expired identity assertion')


def identity(request):
    key = os.getenv('IDENTITY_SIGNING_KEY', '')
    if len(key) < 32:
        raise HTTPException(503, 'Secured mode requires a separate identity signing key')
    token = request.headers.get('x-identity-assertion', '') or request.cookies.get('gz_identity', '')
    if not token and not request.url.path.startswith('/assist-api/'):
        token = request.headers.get('authorization', '').removeprefix('Bearer ')
    claims = verify(token, key)
    from server import app
    initialize_access()
    with app.conn() as db:
        revoked=db.execute('SELECT 1 FROM revoked_assertions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        epoch=db.execute('SELECT revoked_before FROM subject_epochs WHERE subject=?',(claims['sub'],)).fetchone()
    if revoked or (epoch and claims['iat']<=epoch['revoked_before']):
        raise HTTPException(401,'Identity assertion was revoked')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.cookies.get('gz_identity') and not request.headers.get('x-identity-assertion'):
        origin = request.headers.get('origin', '')
        if not origin or urlsplit(origin).netloc != request.headers.get('host') or urlsplit(origin).scheme != request.url.scheme:
            raise HTTPException(403, 'Same-origin request required')
    return claims


def enforce(request):
    from server import app
    if os.getenv('SECURITY_MODE', 'local-demo') != 'signed':
        return None
    path = request.url.path
    if path.startswith(('/health', '/ready', '/mock/', '/browser-lab/','/assist/', '/assist-config', '/assist.js', '/assist.css', '/app.js', '/app.css','/browser-workbench')) or path == '/':
        return None
    if path.startswith(('/integration/', '/core-browser/')):
        # Integration endpoints independently require the service key.
        return None
    claims = identity(request)
    with app.conn() as db:
        db.execute('CREATE TABLE IF NOT EXISTS session_owners (session_id TEXT PRIMARY KEY, subject TEXT NOT NULL)')
        parts = path.strip('/').split('/')
        sid = parts[2] if len(parts)>=3 and parts[0]=='api' and parts[1] in ('sessions','browser-contexts') else (parts[1] if parts[0] == 'session' and len(parts) >= 2 else None)
        if sid:
            owner = db.execute('SELECT subject FROM session_owners WHERE session_id=?', (sid,)).fetchone()
            assignment = db.execute('SELECT 1 FROM operator_assignments WHERE session_id=? AND subject=? AND expires>?',(sid,claims['sub'],time.time())).fetchone() if claims['role']=='operator' else None
            if not owner or (claims['role'] != 'core' and owner['subject'] != claims['sub'] and not assignment):
                raise HTTPException(403, 'Session access denied')
        if path.startswith('/assist-api/'):
            from server.integration import task
            task_id = parts[1]
            human = task(task_id)
            owner = db.execute('SELECT subject FROM session_owners WHERE session_id=?', (human['session_id'],)).fetchone()
            if not owner or owner['subject'] != claims['sub']:
                raise HTTPException(403, 'Verification recipient mismatch')
    if claims['role'] == 'operator' and request.method not in ('GET', 'HEAD'):
        raise HTTPException(403, 'Operator access is read-only')
    return claims


def initialize_access():
    from server import app
    with app.conn() as db:
        db.executescript('CREATE TABLE IF NOT EXISTS revoked_assertions (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL); CREATE TABLE IF NOT EXISTS subject_epochs (subject TEXT PRIMARY KEY, revoked_before REAL NOT NULL); CREATE TABLE IF NOT EXISTS operator_assignments (session_id TEXT, subject TEXT, expires REAL NOT NULL, PRIMARY KEY(session_id,subject));')
