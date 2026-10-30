"""Local synthetic SQLite backup/validation. Restore requires stopped services."""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

MAX_BYTES=64*1024*1024

def encrypted_backup(source,destination):
    from server.storage import pack
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('Choose a new backup path distinct from the source')
    with sqlite3.connect(f'file:{source.resolve().as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(':memory:') as snapshot:
        src.backup(snapshot)
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Database integrity check failed')
        if snapshot.execute('PRAGMA page_count').fetchone()[0]*snapshot.execute('PRAGMA page_size').fetchone()[0]>MAX_BYTES:
            raise ValueError('Snapshot exceeds bounded encrypted backup size')
        encrypted=pack(snapshot.serialize(),'database-backup:v1')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as f:
        f.write(encrypted)

def restore_backup(source,destination):
    from server.storage import unpack
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('Restore only to a new offline database path')
    if source.stat().st_size>MAX_BYTES*2:
        raise ValueError('Encrypted backup exceeds size limit')
    raw=unpack(source.read_bytes(),'database-backup:v1')
    if len(raw)>MAX_BYTES:
        raise ValueError('Decrypted backup exceeds size limit')
    with sqlite3.connect(':memory:') as validated:
        validated.deserialize(raw)
        if validated.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Restore integrity validation failed')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb'):
            pass
        try:
            with sqlite3.connect(destination) as dst:
                validated.backup(dst)
        except Exception:
            destination.unlink(missing_ok=True)
            raise


def backup(source, destination):
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError('Choose a new backup path distinct from the live database')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f'file:{source.resolve().as_posix()}?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup failed integrity validation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--restore',action='store_true')
    parser.add_argument('--plaintext-synthetic',action='store_true')
    args = parser.parse_args()
    if args.restore:
        restore_backup(args.source,args.destination)
    elif args.plaintext_synthetic:
        backup(args.source,args.destination)
    else:
        encrypted_backup(args.source,args.destination)
    print('Database operation passed integrity validation. Restore never overwrites a live/existing database.')
