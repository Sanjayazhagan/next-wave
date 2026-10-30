"""Deletes synthetic sessions older than 30 days. Run in scheduled trusted maintenance.
Cannot delete active worker contexts in a separate process; use API delete first for live sessions.
REAL PII processing not supported. Security-log legal retention is a separate policy.
"""
import os, sqlite3
from pathlib import Path
from datetime import datetime,timezone,timedelta
root=Path(__file__).resolve().parent.parent
path=Path(os.getenv('DATABASE_PATH',root/'data'/'demo.db'))
if not path.exists():print('No demo database');raise SystemExit(0)
cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
with sqlite3.connect(path) as db:
    ids=[r[0] for r in db.execute('SELECT id FROM sessions WHERE created_at < ?', (cutoff,)).fetchall()]
    for sid in ids:
        db.execute('DELETE FROM audit WHERE session_id=?',(sid,))
        db.execute('DELETE FROM sessions WHERE id=?',(sid,))
    db.execute('DELETE FROM demo_receipts WHERE created_at < ?', (cutoff,))
    db.commit()
print('Deleted',len(ids),'expired synthetic sessions')
