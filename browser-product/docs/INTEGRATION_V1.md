# Browser human-assistance integration v1

Implemented local synthetic boundary; not a production identity or WhatsApp integration. Production startup remains disabled. Existing demo APIs are loopback-only scaffolding, not authenticated multi-user APIs.

Run `start-local.cmd`, then `.venv\Scripts\python.exe scripts/simulate_handoff.py`. The simulator prints a local invitation instead of sending WhatsApp. Open it, press Open verification, answer the synthetic challenge manually and observe completion. Do not share invitations; they grant limited demo task access.

Core creates a task:

```http
POST /integration/v1/human-tasks
X-Internal-Key: <configured service key>
Content-Type: application/json

{"session_id":"<canonical demo session id>","ttl_seconds":300}
```

Response: `task_id`, `kind`, `mode`, `expires_at`, and relative `assistance_path`. Core combines the path with a configured trusted public origin. Do not derive the origin from untrusted Host headers. GET previews never consume invitations. The invitation lives in the fragment and is removed before the explicit claim. Tokens are hashed in SQLite and never included in audit events. Claim returns a memory-only scoped bearer; page reload intentionally requires a fresh invitation.

Core polls `GET /integration/v1/events/{session_id}?after=<cursor>` with service authentication. Events include version, session_id, sequence, event_id, timestamp, kind, summary and data. Persist the next_cursor only after processing; deduplicate event_id. `human_task_completed` signals a portal-observed success. `human_task_failed` requires help/new task. These events live in SQLite audit and can be reread after restart; no background callback delivery is claimed. SSE additionally accepts Last-Event-ID or after.

`GET /integration/v1/human-tasks/{task_id}` returns state, expiry and attempt count. Invitations expire, replacement revokes earlier ones, browser changes invalidate them, and three rejected answers close the task. Unknown response outcomes are marked needs_reconciliation; core must inspect live state rather than replay an answer. Answers are never stored in task/audit records.

The worker endpoint `GET /sessions/{id}/challenge` requires the internal key and returns a focused live image and supported interaction type. Currently only the fictional portal's text challenge is supported. This does not claim support for third-party interactive CAPTCHA widgets, remote pointer control, official device authentication or production WhatsApp return links.

During an offered/claimed challenge, public demo mutations are blocked. The task answer uses the dedicated human endpoint internally, then emits an observed result. There is no generic task permission for filling arbitrary fields or submitting an application.

Before production: integrate core user identity/recipient verification (forwardable invitations alone are insufficient), real adapter challenge compatibility, remote-control leases for interactive widgets, cancellation/reconciliation UI, task cleanup scheduling, global rate limiting, encrypted artifacts, audited ownership and production service authentication. Keep this local synthetic demo isolated until then.

Schemas under contracts/v1 are generated from actual Pydantic request models using `scripts/export_contracts.py`; they remain proposals pending team agreement. The running FastAPI OpenAPI describes the complete implemented surface.

Verification: `scripts/verify_handoff.py` starts isolated API/worker processes on ports 8200/8201 with a temporary DB, opens the mobile page in Chromium, solves the challenge and continues the same browser through review/approved mock receipt. Evidence lives in output/human-handoff. It never sends a WhatsApp message or uses real data.
