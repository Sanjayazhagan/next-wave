"""Durable single-use submit-task ledger and trusted public assistance origin."""
import json
import os
import re
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from server.storage import seal,unseal

def public_origin(request=None):
    configured=os.getenv('PUBLIC_BASE_URL','').strip()
    host=os.getenv('DEMO_HOST','').strip()
    if configured or host:
        candidate=configured or 'https://'+host
        try:
            p=urlsplit(candidate)
            valid=p.scheme=='https' and p.hostname and not re.search(r'[\s\\]',candidate) and not p.username and not p.password and p.path in ('','/') and not p.query and not p.fragment and p.port in (None,443)
        except ValueError:valid=False
        if not valid:raise HTTPException(503,'Configure PUBLIC_BASE_URL or DEMO_HOST as a public HTTPS origin without path or credentials')
        return candidate.rstrip('/')
    if os.getenv('APP_MODE')=='integrated' or os.getenv('SECURITY_MODE')=='signed':raise HTTPException(503,'Set PUBLIC_BASE_URL or DEMO_HOST to the deployed public HTTPS origin')
    if request is not None and request.url.hostname in ('127.0.0.1','localhost','testserver'):return str(request.base_url).rstrip('/')
    if request is not None:raise HTTPException(503,'Set DEMO_HOST or PUBLIC_BASE_URL before issuing public assistance links')
    return ''

def persist(task_id,result):
    from server.core_assist import api
    payload=seal(json.dumps(result,separators=(',',':')),'core-submit:'+task_id)
    state=result.get('state','uncertain')
    if state not in ('completed','uncertain','review_changed','rejected'):state='uncertain'
    with api().conn() as db:
        current=db.execute('SELECT state FROM core_assist_tasks WHERE id=?',(task_id,)).fetchone()
        if current and current['state']!='completed':
            db.execute('INSERT OR REPLACE INTO core_assist_results VALUES (?,?)',(task_id,payload))
            db.execute("UPDATE core_assist_tasks SET state=?,token_hash='' WHERE id=?",(state,task_id))

def stored(task_id):
    from server.core_assist import api
    with api().conn() as db:row=db.execute('SELECT payload FROM core_assist_results WHERE task_id=?',(task_id,)).fetchone()
    return json.loads(unseal(row['payload'],'core-submit:'+task_id)) if row else {}

async def control(entry,req):
    from server.core_assist import api
    if req.kind!='click' or req.value or req.x is not None or req.y is not None:raise HTTPException(403,'Submit link permits only its reviewed final button')
    if not req.observation_id or not req.target_ref:raise HTTPException(422,'Current view observation_id and target_ref are required')
    # Claim BEFORE sending anything to the worker. Concurrent/replayed tokens
    # cannot dispatch a second browser operation, even after API restart.
    with api().conn() as db:
        changed=db.execute("UPDATE core_assist_tasks SET state='submitting',token_hash='' WHERE id=? AND state='active' AND expires>strftime('%s','now')",(entry['id'],)).rowcount
    if changed!=1:raise HTTPException(403,'Submit link has already been used or expired')
    try:
        result=await api().worker('POST',f'/core/session/{entry["session_id"]}/human-act',{**req.model_dump(),'task_id':entry['id']},timeout=45)
        persist(entry['id'],result)
        return result
    except HTTPException as exc:
        known=(exc.headers or {}).get('X-Browser-Outcome')=='not_applied'
        state=('review_changed' if exc.status_code==409 else 'rejected') if known else 'uncertain'
        persist(entry['id'],{'state':state,'confirmed_by_portal':False,'receipt_number':None,'click_attempted':not known,'needs_reconciliation':not known,'needs_new_review':state=='review_changed','reason':'New review required' if known else 'Worker response unavailable; reconcile before any new submission'})
        raise
    except BaseException:
        persist(entry['id'],{'state':'uncertain','confirmed_by_portal':False,'receipt_number':None,'click_attempted':True,'needs_reconciliation':True,'reason':'Submission response lost; reconcile before any new submission'})
        raise

async def status(entry):
    from server.core_assist import api
    result=stored(entry['id']) or {'confirmed_by_portal':False,'receipt_number':None,'needs_reconciliation':False}
    if entry['state'] in ('active','offering','submitting','uncertain','needs_reconciliation'):
        try:
            live=await api().worker('GET',f'/core/session/{entry["session_id"]}/human-status')
            if live.get('task_id')==entry['id'] and live.get('result'):
                result=live['result'];persist(entry['id'],result)
            elif live.get('task_id')!=entry['id'] or entry['state']=='submitting':
                result={'state':'uncertain','confirmed_by_portal':False,'receipt_number':None,'needs_reconciliation':True,'reason':'Task outcome needs reconciliation'};persist(entry['id'],result)
        except HTTPException:
            if entry['state'] not in ('active','offering') or entry.get('expires',0)>time.time():
                result=result or {'state':'uncertain','confirmed_by_portal':False,'receipt_number':None,'needs_reconciliation':True,'worker_available':False};persist(entry['id'],result)
    return {**entry,**result,'reason':entry['reason'],'outcome_reason':result.get('reason'),'task_id':entry['id']}
