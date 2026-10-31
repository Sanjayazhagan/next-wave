# Audit fixes — 1 November 2026

Scope: only `next-wave-browser-update/browser-product`. The main agent,
credentials, existing environment files and Azure deployment are not changed.

## Changes

- Assistance ownership/expiry is checked again inside the browser lock before
  view, control and completion. Expired ownership can be replaced directly.
  Close and approval changes are serialized with actions; closed contexts are
  rejected. Idle-reaped contexts also remove their bridge records.
- Core and human OTP verification use one five-attempt counter. A core-entered
  value is bound to its observed frame/form. OTP send limits remain separate.
- Core action requests accept `action_id`; **integrated mode requires it**.
  Same ID/body returns the saved result without another portal action. Changed
  input is refused. The per-context ledger never evicts IDs to allow accidental
  replay; after 1,000 entries it requires reconciliation/closure. Request
  fingerprints use an ephemeral HMAC, not stored raw codes or file contents.
  A timeout/failure after a possible side effect blocks further actions. Read
  snapshots remain available for reconciliation; no automatic retry/submit is
  performed. Worker restart loses the context and returns missing-session
  errors rather than replaying effects into a new browser.
- The supplied core client generates stable action IDs and retains an unresolved
  action after a lost response. Another step is refused until that uncertainty
  is handled. `retry_pending(sid)` sends the identical request/ID to retrieve
  the worker's result when possible. Core must persist IDs/state in its own
  durable graph for recovery across core/client restarts. Do not log payloads.
- Legacy, v2 tool and artifact uploads share filename, size, MIME, image
  signature/dimension and extension validation. PDF checking remains a signature
  check, not malware scanning or full document semantic validation.
- Submit input values are included in visible labels; actual bracketed names
  are retained. Dedicated upload POST permission is exact-target, single-use
  and briefly waits for an asynchronously dispatched request. Unknown/final
  application controls remain blocked. The core must still inspect the portal
  confirmation; `confirmed_by_portal:false` is intentional.
- Assistance DB state exists before worker pause, with offering/completing/
  needs_reconciliation states for interrupted cross-process operations. Polling
  checks worker ownership; it does not turn ambiguous completion into success.
- Both browser setup paths clean failed contexts. Service workers are blocked,
  WebSockets are closed, and excess tabs are closed (default 8, configurable
  `MAX_BROWSER_TABS`, range 1–32). The Docker image runs as `pwuser`.
- API Compose mappings now pass `DEMO_HOST`; source packaging includes the
  integrated overlay. Screenshot/test-result exclusions apply to Git and Docker.
  New assistance records/orphan audit history have retention, metrics have
  separate bridge families/aggregate task states, and an alert covers handoff
  reconciliation. Known dangerous GET route patterns are blocked conservatively.

## Core integration change

Every integrated action must include a stable UUID (or another 8–100 character
ID) chosen **before** sending the request:

```json
{"action_id":"<stable-uuid>","type":"click","target":{"role":"button","name":"Upload"}}
```

Reuse that ID and the exact body only to reconcile/retrieve the result of that
same operation. A changed decision gets a new ID only after the prior outcome
is known. Do not retry an uncertain action with a new ID or reopen/replay an
application merely because the client timed out. Use the supplied helper or
make this localized change in the existing core browser client; no replacement
of LangGraph nodes or the teammate's main is included.

Human tasks remain recipient-bound by the authenticated chat service. The core
must send the private assistance URL to the verified citizen, pause planning,
poll completion and inspect the live page afterward. Citizen attestation is
not proof of authentication or submission success.

## Deployment checks still required

- Set `DEMO_HOST` to the actual HTTPS hostname. Set `TRUSTED_PROXY_IPS` only to
  the actual reverse proxy IP or private CIDR, never an unreviewed wildcard.
  Verify HTTPS cookies, forwarded scheme/client IPs and Caddy on the real host.
- Existing Docker data volumes created by root may need an operator-reviewed
  ownership migration for `pwuser`. Back up encrypted state/keys first. The
  new Docker image/user and Compose runtime were not executed on this host.
- Put browser workers behind network-level egress isolation. JS/Playwright
  checks, service-worker blocking and an unprivileged container do not establish
  a complete anti-DNS-rebinding or browser-exploit boundary. Chromium still
  uses the existing no-sandbox launch configuration; a supported sandbox/seccomp
  deployment requires platform validation.
- Do not enable arbitrary public user access or generic final submission.
  Site-controlled button labels, upload paths and GET methods cannot prove
  that a server operation is harmless. Real writes/receipts need reviewed
  adapters, authorization and observed evidence.
- Test actual model/chat integration, real portal OTP/CAPTCHA, restart/recovery,
  proxy behavior, capacity and long-running operation on staging. These local
  synthetic checks cannot certify a live Azure service or all websites.

There is no cloud deployment claim and no assertion that these controls alone
make the service production ready.

## Verification evidence

Final full regression: **93 passed**, one upstream Starlette/httpx deprecation
warning, 307.19 seconds. Real local API/worker checks also passed:
`scripts/verify_handoff.py`, `scripts/verify_general_browser.py`, and
`scripts/verify_conversation.py` (including the Node transport example).
Python syntax and assistance JavaScript syntax passed. All data was synthetic;
no model/provider messages were sent. Docker/Azure runtime was not tested.
