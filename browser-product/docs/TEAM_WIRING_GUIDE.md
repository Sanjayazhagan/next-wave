# Browser/product integration handoff

**Citizen conversation bridge:** read CONVERSATION_WIRING.md. /integration/v2/conversation and Python/Node clients provide generation/subject-bound questions, encrypted delivery leases/ACKs, correlated replies, pause enforcement, transient v1 OTP/CAPTCHA routing and declared-review decisions. scripts/verify_conversation.py verifies an actual local browser plus a fake message consumer. No WhatsApp provider, agent or real portal adapter is silently supplied.

Latest additions: encrypted artifact upload/reference/delete, core-controlled identity revocation and operator assignment, Secure/HttpOnly identity-cookie exchange, human help/reconciliation and a validated return URL, plus an executable Node client. Read OPERATIONS_AND_SECURITY.md for keys, migrations, encrypted backup/restore and monitoring. `scripts/verify_release.py` tests the full Python/Node synthetic wiring against isolated services. Some older limitation statements below describe the prior pass and are superseded by the operations guide and RELEASE_STATUS.md.

This service executes browser work. Core remains the owner of LangGraph, conversation, WhatsApp, eligibility/doctor decisions, skills and citizen approval. Remote supplies prepared/verified inputs. No external message is sent by this repository.

## Start and modes

Use `start-local.cmd` on Windows or `python scripts/run_local.py` elsewhere after installing `requirements.lock` and Playwright Chromium. Default API/worker ports are 8100/8101; API_PORT and WORKER_PORT override them. Docker uses compose.yaml; its latest healthcheck/image changes are prepared but not locally built because Docker is unavailable.

`APP_MODE=demo` is the only enabled runtime. Unsupported production mode fails at startup. `SECURITY_MODE=local-demo` is only for loopback synthetic testing. `SECURITY_MODE=signed` enforces identity assertions and ownership on legacy citizen/operator endpoints; it does not make synthetic portal code production-ready.

Set independent random INTERNAL_KEY, APP_SIGNING_KEY and IDENTITY_SIGNING_KEY (at least 32 characters). Never expose the worker or share INTERNAL_KEY with citizens. Core-issued identity is separate from the service credential.

## Core API

All `/integration/v1/*` endpoints require `X-Internal-Key`. The trusted core may access its managed sessions; this is a service-to-service boundary, not a citizen-facing credential.

1. `GET /integration/v1/portals`: supported adapter modes, constraints and disabled official candidates.
2. `POST /integration/v1/sessions`: BrowserStart input from contracts/v1/browser-start.schema.json. Supply request_id, subject, consent_ref and exactly five verified fields. Each field has value, source_ref, confidence and verified. Only mock-scholarship/demo is accepted. Core must validate actual consent, eligibility and doctor decisions upstream; a reference alone is not independent proof.
3. Persist the returned browser session ID in the core graph. Retrying the same request_id and inputs returns the same ID. A changed request with an old ID fails. A pending start is not blindly replayed; reconcile it operationally.
4. `POST /integration/v1/sessions/{id}/commands`: action_id, expected_state, kind and payload. Supported kinds: otp, human, fill, approve, edit, resume, reconcile, poll, inject, action. See actual schemas and OpenAPI. Reusing a completed action ID returns the saved result. Pending/unknown outcomes fail closed. Use a new ID for a deliberate corrected attempt; inspect live state first.
5. `GET /integration/v1/sessions/{id}`: persisted execution state.
6. `GET /integration/v1/events/{id}?after=N`: durable ordered events and next_cursor. Deduplicate event_id; checkpoint the cursor after processing. This is pull-based at-least-once consumption, not a guaranteed callback push service. SSE also resumes using Last-Event-ID.

OTP and challenge answers are passed directly to the worker and never stored as command payloads or low-entropy hashes. Core must likewise exclude them from LangGraph checkpoints and WhatsApp workflow execution logs.

Use `clients/browser_client.py` with `server/contracts.py` in the shared repository. The async client wraps the same public contract and deliberately does not retry unknown side effects automatically. Schemas under contracts/v1 can be consumed from other languages; the server's `/openapi.json` is the implemented surface.

Example start body:

```json
{"request_id":"unique-start-001","subject":"synthetic-citizen","consent_ref":"synthetic-consent","portal":"mock-scholarship","mode":"demo","fields":{"student_name":{"value":"Kavya Demo","source_ref":"synthetic-answer","confidence":1,"verified":true},"course":{"value":"B.Tech","source_ref":"synthetic-answer","confidence":1,"verified":true},"income":{"value":"120000","source_ref":"synthetic-document","confidence":1,"verified":true},"state":{"value":"Tamil Nadu","source_ref":"synthetic-answer","confidence":1,"verified":true},"category":{"value":"BC","source_ref":"synthetic-document","confidence":1,"verified":true}}}
```

Example OTP command:

```json
{"action_id":"unique-action-001","expected_state":"otp_needed","kind":"otp","payload":{"otp":"246810"}}
```

## Remote documents and provenance

Supply verified profile fields at start. Their supplied source references are returned by the field-provenance endpoint. An explicit review edit changes their provenance to citizen-approved-edit; it must not continue claiming that a changed value came from the original certificate.

A fill command can include a PreparedDocument payload: subject, source_ref, safe PDF file_name and file_base64. Subject must match session ownership. The enabled adapter accepts PDF <=1 MB; these are fictional constraints, not government limits. Input encoding/type/size and filename are validated. Bytes are relayed to the browser, not written to application storage or action logs. Future real document delivery should integrate the core vault/artifact service; no arbitrary external file URLs are accepted. An empty fill payload explicitly uses a synthetic fixture in demo mode.

## Human handoff

Core observes captcha_needed, creates `/integration/v1/human-tasks`, then sends its returned assistance path using a configured trusted origin. The server does not construct public URLs from Host or send WhatsApp messages.

Claiming requires an explicit button action; link previews do not consume the task. The page removes the invitation fragment and uses an in-memory task bearer. It shows a focused live challenge image and supports direct normalized pointer clicks, text to the focused field and restricted keys. Frames expire after 30 seconds and geometry/stage must still match. Every human action is restricted to the challenge step and invalidates the frame. No final-submit control is granted.

The page also supports the simple screenshot/text-answer path. Successful portal observation produces human_task_completed; clicking a Done button or returning to WhatsApp does not prove completion. Core resumes from the event. Three rejected simple answers close the task. Cancel/reissue through the authenticated API. Expiry, stale browser generation and ambiguous actions are explicit states.

Signed mode additionally requires the recipient's core-issued identity, matching the session owner. A trusted identity gateway can establish `gz_identity` as a Secure/HttpOnly/SameSite cookie or supply `X-Identity-Assertion` on assistant API calls. Assertions are HMAC-signed by the separate identity key, with sub, role (citizen/operator/core), aud=gradientzero-browser and exp <=15 minutes. Cookie writes require same-origin requests. Core must validate its actual user before issuing an assertion; there is no built-in login/directory. The default local page needs no identity only because it is synthetic and loopback-scoped.

Do not claim compatibility with every official CAPTCHA: widgets, iframe origins, required full-page views, device/face-auth and actual portal challenge regions need adapter-specific verification. The tested direct-control adapter is fictional.

## Approval and recovery

Review readback is compared with the verified profile and hashed. Core obtains a citizen decision for that exact review. Approve command requires confirmed=true and the current review_hash. Editing invalidates the hash. Generic actions only mutate the application-form stage, not login/challenge/review/submission.

Session mutations use a SQLite execution lease across API processes (120 seconds). Worker actions also serialize on context locks; browser creation is capacity-locked. This is a single-host SQLite design, not a multi-region worker queue.

Worker death requires resume, fresh human login and review; it does not resurrect authentication. An approval begins by persisting submission_uncertain. A timeout must be reconciled, not blindly repeated. The fictional portal uses a stable idempotency key tied to the session, and reconcile consults its receipt store. A real adapter must replace that fixture reconciliation with authoritative portal observations before it can be enabled.

## Operations and release gates

`/ready` verifies database access and Chromium connectivity. Authenticated `/integration/v1/metrics` returns aggregate states without citizen data. Idle worker contexts close after MAX_BROWSER_IDLE_SECONDS (default 900); active context count defaults to at most 8. Actual supported production capacity remains unmeasured.

Synthetic retention runs every 60 seconds and removes service records older than 30 days after worker cleanup succeeds. This covers this DB only, not core vault, WhatsApp, external artifacts or backups. Expired tasks are revoked. Unknown in-flight human outcomes require reconciliation. Use scripts/database_ops.py for an integrity-checked SQLite copy to a new path. Restore only to a distinct offline path with services stopped, validate integrity, then configure DATABASE_PATH to that copy. Backup encryption/storage/access/deletion is an external operational requirement, not implemented by a plaintext SQLite copy.

Tests: pytest; scripts/verify_handoff.py; scripts/verify_resilience.py; scripts/verify_local.py against running services. CI runs unit/browser/HTTP/restart checks using requirements.lock. Deployment remains deferred. Real adapter coverage, verified teammate integration, production identity provisioning, encrypted real-data persistence, security/load review and Mumbai Docker/HTTPS evidence remain release gates. No real application or production readiness is claimed by synthetic tests.
