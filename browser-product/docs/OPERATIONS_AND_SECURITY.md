# Browser-owned data, access and operations

This service remains a synthetic local/integration implementation. These controls do not independently certify production readiness, official portal compatibility or all-system privacy compliance.

Conversation transport now encrypts requests, non-secret replies, leased deliveries and provider references; transient OTP/challenge answers are never persisted in its ledger. Consumer deduplication, trusted subject mapping and provider webhook verification are core-owned. Key rotation and context deletion include these records. See CONVERSATION_WIRING.md for expiry, acknowledgement, pause and reconciliation rules.

## Local configuration

`python scripts/configure_local.py` creates data/local-config.json with independent service, approval, identity and Fernet encryption keys. It refuses to overwrite an existing file and never prints secrets. The local launcher loads that file; inherited environment variables take precedence. The data directory is ignored by Git and excluded from release archives. File mode is restricted where supported; verify the actual Windows ACL or deployment secret mount yourself. Do not distribute this configuration with source code.

The default configuration is encrypted local-demo: synthetic data only, loopback service, no citizen login. `--signed` prepares signed access integration; the dashboard then needs a core-issued identity session. There is no fabricated production identity provider or account directory.

Optional environment: DATA_ENCRYPTION_KEYS, SECURITY_MODE, INTERNAL_KEY, APP_SIGNING_KEY, IDENTITY_SIGNING_KEY, ALLOWED_HOSTS, MAX_REQUEST_BYTES, REQUEST_BODY_TIMEOUT_SECONDS, MAX_BROWSER_SESSIONS, MAX_BROWSER_IDLE_SECONDS and WHATSAPP_RETURN_URL. Configured keys must remain outside source/logs. Signed mode rejects short/default/shared identity/service/approval keys and requires encryption. Runtime other than APP_MODE=demo remains blocked.

## Encryption and migration

Profiles and provenance/consent records are encrypted when DATA_ENCRYPTION_KEYS is configured. Prepared artifacts always require encryption; retaining them without keys fails. Scope is authenticated inside each envelope, so moving a profile/artifact ciphertext to another session cannot make it valid there. Artifact filenames/source metadata are encrypted; size and operational IDs/timestamps are not secret. SQLite tables/indexes, opaque identity subjects, timestamps, routing IDs and event summaries remain metadata, not full-disk encryption. Core subjects should be pseudonymous IDs, never Aadhaar/bank/phone numbers.

Encryption uses cryptography Fernet/MultiFernet, not custom cipher construction. Fernet exposes token time and keeps each message in memory, so artifacts are capped at 1 MB and encrypted backups at a 64 MB source snapshot. See the [library's authenticated encryption and rotation documentation](https://cryptography.io/en/latest/fernet/).

To migrate a legacy synthetic database, stop API and worker first, configure the keys, and run:

```powershell
python scripts/migrate_storage.py data/demo.db output/backups/before-migration.enc
```

The tool makes a verified encrypted snapshot first, then encrypts fields and compacts the DB/WAL. It never claims to erase earlier filesystem snapshots, SSD remnants or separately created plaintext backups. Signed mode refuses to read a legacy plaintext sensitive record; migrate deliberately rather than silently accepting it.

For rotation, set DATA_ENCRYPTION_KEYS to NEW_KEY,OLD_KEY (new first), stop services and run the migration tool with `--rotate-existing` and a new backup path. This rotates profiles, provenance, consent and artifact bodies/metadata. Test restore before retiring old keys. Old backups may contain records encrypted under older keys even when their outer backup envelope uses the new key; retain required decryption keys securely until those backups expire or are migrated. Never lose the only decryption key.

## Backups and restore

```powershell
python scripts/database_ops.py data/demo.db output/backups/browser.enc
python scripts/database_ops.py output/backups/browser.enc output/restored/browser.db --restore
```

Backup is encrypted by default and validates SQLite integrity. Restore decrypts/validates in memory and only writes a new path; it refuses to overwrite the live or an existing database. `--plaintext-synthetic` is an explicit compatibility option for synthetic-only copies. Do not use it for citizen records. Backups are separate retention objects; implement provider/storage access rules and an expiry schedule before deployment. Automated application cleanup cannot delete unknown external copies.

DB user_version is checked to refuse unsafe application downgrades. Offline sensitive-field migration is recorded in schema_migrations. This is a single-host SQLite implementation; distributed leases, database HA and cross-region guarantees are not claimed.

## Identity and operator access

Core signs short-lived assertions with subject, role, audience, issue/expiry times and token ID. Identity verification checks signature/expiry/audience, explicit token revocation and subject revocation epoch. `POST /auth/session` exchanges an already verified bearer assertion for a Secure/HttpOnly/SameSite=Strict cookie. Real HTTPS is required for that cookie. No insecure-cookie fallback is enabled. Cookie mutations require matching Origin scheme and host, including when a task bearer is also present. POST /auth/logout revokes the presented assertion and expires the cookie.

Authenticated core can revoke all previously issued assertions for a subject via POST /integration/v1/identity/revoke. New assertions issued after revocation can be accepted; core is responsible for deciding whether to reauthenticate that user. Core can create temporary, session-specific read-only operator assignments via /integration/v1/sessions/{id}/operators and revoke them. Operator tokens never authorize mutation or final submission. All /integration/v1 routes use a separate server-to-server credential and must never be called with that credential from a citizen browser.

## Requests and logs

RequestBoundary buffers at most the configured byte limit before any route runs, validates declared length, counts chunked bytes and imposes a body-read timeout. This prevents partial oversized input from triggering actions. TrustedHost validates intended hosts. Task POST actions have a per-client hashed-address rate limit; edge WAF/distributed abuse protection and real user traffic validation remain deployment requirements. This is not a claim of unlimited denial-of-service resilience.

No OTP/challenge payload or low-entropy answer hash is stored in durable command rows. Browser snapshots mask password/one-time input fields, and rejected OTP inputs are cleared. Real adapters still need portal-specific redaction checks before real identifiers/documents are handled. Never enable real browser tracing/video with citizen credentials; the supplied recording uses synthetic fixtures only.

## Monitoring and alerts

- /health: process liveness; /ready: DB + connected Chromium.
- /integration/v1/metrics: aggregate state JSON; /integration/v1/metrics/prometheus: low-cardinality HTTP counters/duration sums and state gauges. Both metrics routes require X-Internal-Key. No labels contain session/user IDs or request bodies. Process HTTP counters reset on restart.
- scripts/monitor_service.py: one bounded readiness/metrics check; exits 2 and emits redacted alert codes for unavailability or uncertain outcomes. Set BASE_URL and INTERNAL_KEY through secret configuration. It sends no external notifications.
- deploy/alerts.yaml: example alert rules for service availability and uncertain submissions/human tasks. Integrate into the team's actual monitoring/notification system; no alert receiver is configured or tested here.

Synthetic retention runs each minute, expires tasks/access grants/artifacts and deletes service records older than 30 days after context cleanup succeeds. A worker cleanup failure preserves the record for retry. This does not prove deletion from WhatsApp, core vault, OS/browser swap, logs, storage snapshots or backups. User-initiated successful session deletion removes associated encrypted artifacts, provenance, tasks, commands and access grants too.

## Operational response

An ambiguous submission stays submission_uncertain. Do not retry final submit; reconcile the actual portal first. A stale in-flight human task becomes needs_reconciliation. The core reconcile endpoint checks live browser state; if still on the challenge it revokes access and requires a new invitation. A missing browser needs fresh human authentication and review. Readiness failures, cleanup failures and growing pending states require operator investigation, not silently fabricated success.

Before a real release: install and test Docker, verify Mumbai and HTTPS, wire actual core/remote/identity/vault/notification services, verify permitted official adapters, measure capacity under the real load, test restore/rollback in the deployed environment and perform a security/privacy review. These are real release gates despite the passing local synthetic tests.
