"""Offline sensitive-field migration. Makes an encrypted backup before mutation."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.storage import cipher,seal,rotate,PREFIX
from scripts.database_ops import encrypted_backup


def migrate(path,backup_path,rotate_existing=False):
    cipher()  # Fail before changing anything if keys are unavailable.
    encrypted_backup(path,backup_path)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA secure_delete=ON')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)')
        for sid,value in db.execute('SELECT id,profile FROM sessions').fetchall():
            if not value.startswith(PREFIX) or rotate_existing:
                db.execute('UPDATE sessions SET profile=? WHERE id=?',(rotate(value) if value.startswith(PREFIX) else seal(value,f'profile:{sid}'),sid))
        if 'provenance' in tables:
            for sid,fields,consent in db.execute('SELECT * FROM provenance').fetchall():
                db.execute('UPDATE provenance SET fields=?,consent_ref=? WHERE session_id=?',((rotate(fields) if rotate_existing else fields) if fields.startswith(PREFIX) else seal(fields,f'provenance:{sid}'),(rotate(consent) if rotate_existing else consent) if consent.startswith(PREFIX) else seal(consent,f'consent:{sid}'),sid))
        if rotate_existing and 'artifacts' in tables:
            for ident,metadata,body in db.execute('SELECT id,metadata,body FROM artifacts').fetchall():
                db.execute('UPDATE artifacts SET metadata=?,body=? WHERE id=?',(rotate(metadata),cipher().rotate(body),ident))
        if rotate_existing and 'browser_actions' in tables:
            for context_id,action_id,result in db.execute('SELECT context_id,action_id,result FROM browser_actions WHERE result IS NOT NULL').fetchall():
                db.execute('UPDATE browser_actions SET result=? WHERE context_id=? AND action_id=?',(rotate(result),context_id,action_id))
        if rotate_existing and 'conversation_interrupts' in tables:
            for ident,request,response in db.execute('SELECT id,request,response FROM conversation_interrupts').fetchall():
                db.execute('UPDATE conversation_interrupts SET request=?,response=? WHERE id=?',(rotate(request),rotate(response) if response else None,ident))
        if rotate_existing and 'conversation_deliveries' in tables:
            for ident,payload,ref in db.execute('SELECT id,payload,provider_ref FROM conversation_deliveries').fetchall():
                db.execute('UPDATE conversation_deliveries SET payload=?,provider_ref=? WHERE id=?',(rotate(payload),rotate(ref) if ref else None,ident))
        if rotate_existing and 'conversation_responses' in tables:
            for ident,response_id,result in db.execute('SELECT interrupt_id,response_id,result FROM conversation_responses WHERE result IS NOT NULL').fetchall():
                db.execute('UPDATE conversation_responses SET result=? WHERE interrupt_id=? AND response_id=?',(rotate(result),ident,response_id))
        db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)',(datetime.now(timezone.utc).isoformat(),))
        db.commit()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('VACUUM')
    return {'schema_version':1,'encrypted_backup_created':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database',type=Path);p.add_argument('backup',type=Path)
    p.add_argument('--rotate-existing',action='store_true')
    args=p.parse_args();print(migrate(args.database,args.backup,args.rotate_existing))
