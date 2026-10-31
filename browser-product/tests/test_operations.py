import json
import sqlite3
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
import server.app as app
from server.maintenance import sweep
from scripts.database_ops import backup


@pytest.mark.asyncio
async def test_retention_and_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'DB', tmp_path/'source.db')
    async def worker(*args, **kwargs):
        return {'ok':True}
    monkeypatch.setattr(app,'worker',worker)
    # Initialize schema without leaving the synchronous test client's event loop open.
    with TestClient(app.app):
        pass
    old = (datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    with app.conn() as db:
        db.execute('INSERT INTO sessions(id,worker_id,state,profile,consent_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', ('old','browser','otp_needed',json.dumps(app.DEFAULT_PROFILE),old,old,old))
    result = await sweep(app)
    assert result['deleted_sessions'] == 1
    with app.conn() as db:
        assert not db.execute('SELECT * FROM sessions').fetchall()
    target = tmp_path/'backup.db'
    backup(app.DB,target)
    with sqlite3.connect(target) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with pytest.raises(ValueError):
        backup(app.DB,target)
