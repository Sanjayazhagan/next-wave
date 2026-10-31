"""Owner-scoped encrypted artifact boundary for prepared synthetic PDFs."""
import base64
import time
import uuid
import io
import json
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from server.contracts import PreparedDocument
from server.storage import pack, unpack, seal, unseal

router=APIRouter()


def initialize():
    from server.integration import api
    with api().conn() as db:
        db.execute('CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, metadata TEXT NOT NULL, body BLOB NOT NULL, created REAL NOT NULL, expires REAL NOT NULL)')


@router.post('/integration/v1/sessions/{sid}/artifacts',status_code=201)
async def upload(sid: str, document: PreparedDocument, x_internal_key: str | None=Header(None)):
    from server.integration import api, require_service, initialize as core_initialize
    require_service(x_internal_key)
    core_initialize(); initialize()
    with api().conn() as db:
        owner=db.execute('SELECT subject FROM session_owners WHERE session_id=?',(sid,)).fetchone()
    if not owner or owner['subject']!=document.subject:
        raise HTTPException(403,'Document ownership mismatch')
    try:
        raw=base64.b64decode(document.file_base64,validate=True)
    except Exception:
        raise HTTPException(422,'Invalid document encoding')
    mime=getattr(document,'mime_type','application/pdf')
    from browser.document_validation import validate_document
    validate_document(raw,document.file_name,mime)
    ident=str(uuid.uuid4()); scope=f'artifact:{sid}:{ident}'
    try:
        encrypted=pack(raw,scope)
        metadata=seal(document.model_dump_json(exclude={'file_base64'}),scope+':metadata')
    except RuntimeError:
        raise HTTPException(503,'Configure storage encryption before retaining documents')
    with api().conn() as db:
        db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',(ident,sid,metadata,encrypted,time.time(),time.time()+30*86400))
    return {'artifact_id':ident,'session_id':sid,'mime_type':mime,'expires_in_seconds':30*86400}


def read(sid, ident):
    from server.integration import api
    initialize()
    with api().conn() as db:
        r=db.execute('SELECT * FROM artifacts WHERE id=? AND session_id=? AND expires>?',(ident,sid,time.time())).fetchone()
    if not r:
        raise HTTPException(404,'Artifact missing, expired or outside this session')
    scope=f'artifact:{sid}:{ident}'
    return unpack(r['body'],scope),unseal(r['metadata'],scope+':metadata')


@router.get('/integration/v1/sessions/{sid}/artifacts/{ident}')
async def download(sid: str,ident: str,x_internal_key: str | None=Header(None)):
    from server.integration import require_service
    require_service(x_internal_key)
    raw,metadata=read(sid,ident)
    return Response(raw,media_type=json.loads(metadata).get('mime_type','application/pdf'),headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="prepared-document.bin"'})


@router.delete('/integration/v1/sessions/{sid}/artifacts/{ident}')
async def delete(sid: str,ident: str,x_internal_key: str | None=Header(None)):
    from server.integration import require_service,api
    require_service(x_internal_key);initialize()
    with api().conn() as db:
        db.execute('DELETE FROM artifacts WHERE id=? AND session_id=?',(ident,sid))
    return {'deleted':True}
