"""Retention for this service's synthetic records; no cross-service deletion claim."""
import asyncio
from datetime import datetime, timedelta, timezone
import time


async def sweep(app, at=None):
    at = at or datetime.now(timezone.utc)
    cutoff = (at-timedelta(days=30)).isoformat()
    from server.integration import initialize
    initialize()
    from server.artifacts import initialize as artifact_initialize
    from server.security import initialize_access
    artifact_initialize();initialize_access()
    from server.browser_v2 import initialize as initialize_browser
    initialize_browser()
    from server.conversation_bridge import initialize as initialize_conversation,expire
    initialize_conversation();expire()
    deleted = 0
    with app.conn() as db:
        db.execute("UPDATE human_tasks SET state='expired', bearer_hash=NULL WHERE expires<? AND state IN ('offered','claimed')", (at.timestamp(),))
        db.execute("UPDATE human_tasks SET state='needs_reconciliation', bearer_hash=NULL WHERE expires<? AND state='answering'", (at.timestamp(),))
        db.execute('DELETE FROM artifacts WHERE expires<?',(at.timestamp(),))
        db.execute('DELETE FROM revoked_assertions WHERE expires<?',(at.timestamp(),))
        db.execute('DELETE FROM operator_assignments WHERE expires<?',(at.timestamp(),))
        db.execute('DELETE FROM conversation_deliveries WHERE expires<?',(at.timestamp()-86400,))
        db.execute("DELETE FROM conversation_responses WHERE interrupt_id IN (SELECT id FROM conversation_interrupts WHERE expires<? AND state NOT IN ('pending','processing','needs_reconciliation'))",(at.timestamp()-86400,))
        db.execute("DELETE FROM conversation_interrupts WHERE expires<? AND state NOT IN ('pending','processing','needs_reconciliation')",(at.timestamp()-86400,))
        rows = db.execute('SELECT id,worker_id FROM sessions WHERE created_at<?', (cutoff,)).fetchall()
        general_rows=db.execute('SELECT id,worker_id,state FROM browser_contexts WHERE created<?',(at.timestamp()-30*86400,)).fetchall()
    for row in general_rows:
        if row['worker_id'] and row['state']=='active':
            try:await app.worker('DELETE','/contexts/'+row['worker_id'])
            except Exception:continue
        from server.conversation_bridge import purge_context
        purge_context(row['id'])
        with app.conn() as db:
            db.execute('DELETE FROM browser_actions WHERE context_id=?',(row['id'],))
            for table in ('artifacts','session_owners','audit'):db.execute(f'DELETE FROM {table} WHERE session_id=?',(row['id'],))
            db.execute('DELETE FROM browser_contexts WHERE id=?',(row['id'],))
    for row in rows:
        try:
            await app.worker('DELETE', '/sessions/'+row['worker_id'])
        except Exception:
            # Do not erase the only reference while a live context may still exist.
            continue
        from server.conversation_bridge import purge_context
        purge_context(row['id'])
        with app.conn() as db:
            for table in ('audit','human_tasks','session_owners','provenance','core_commands','artifacts','operator_assignments'):
                db.execute(f'DELETE FROM {table} WHERE session_id=?', (row['id'],))
            db.execute('DELETE FROM core_requests WHERE session_id=?', (row['id'],))
            db.execute('DELETE FROM demo_receipts WHERE idempotency_key=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE id=?', (row['id'],))
        deleted += 1
    with app.conn() as db:
        db.execute('DELETE FROM demo_receipts WHERE created_at<?', (cutoff,))
    return {'deleted_sessions': deleted}


async def loop(app):
    while True:
        await asyncio.sleep(60)
        try:
            await sweep(app)
        except Exception:
            # No raw exceptions/URLs/identifiers in operator logs.
            import logging
            logging.getLogger(__name__).error('Synthetic retention sweep failed; retrying next interval')
