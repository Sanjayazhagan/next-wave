import json
import sqlite3
from cryptography.fernet import Fernet
from scripts.migrate_storage import migrate
from server.storage import unseal,PREFIX
from scripts.database_ops import restore_backup


def test_offline_migration_preserves_data_and_restorable_backup(monkeypatch,tmp_path):
    monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    path=tmp_path/'legacy.db';backup=tmp_path/'before.enc'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,profile TEXT)')
        db.execute('INSERT INTO sessions VALUES(?,?)',('s1',json.dumps({'name':'Synthetic private name'})))
        db.execute('CREATE TABLE provenance(session_id TEXT PRIMARY KEY,fields TEXT,consent_ref TEXT)')
        db.execute('INSERT INTO provenance VALUES(?,?,?)',('s1','{"name":"Synthetic private name"}','consent-reference'))
    result=migrate(path,backup);assert result['encrypted_backup_created']
    with sqlite3.connect(path) as db:
        profile=db.execute('SELECT profile FROM sessions').fetchone()[0]
        assert profile.startswith(PREFIX)
        assert json.loads(unseal(profile,'profile:s1'))['name']=='Synthetic private name'
        assert db.execute('SELECT version FROM schema_migrations').fetchone()[0]==1
    assert b'Synthetic private name' not in path.read_bytes()
    restored=tmp_path/'restored-before-migration.db';restore_backup(backup,restored)
    with sqlite3.connect(restored) as db:
        assert 'Synthetic private name' in db.execute('SELECT profile FROM sessions').fetchone()[0]
