# Architecture and interfaces

## Source-of-truth responsibility split

The uploaded *Forge '26 — GradientZero work split* specifies: browser teammate owns Playwright sessions, screenshots and accessibility snapshots, actions, CAPTCHA/error detection, per-portal logins and re-logins, 2–3 validated portal flows, `/session/{id}/inject`, live web view, provenance, audit, deployment to India-region VM, demonstration recording. Core teammate owns LangGraph orchestrator, approval pauses, saved skills, encrypted vault, WhatsApp/n8n and user conversations. Remote teammate owns extraction, language, compressor, eligibility, doctor, chaos script, benchmark and status watcher.

This repo **implements the browser teammate's demo**, with a tiny replaceable demo coordinator to stand in for the core teammate until merge. The mock portal provides fixture behavior, not actual government integration.

```text
Web client (static HTML/CSS/JS)
  ├── /api/sessions (FastAPI control/demo coordinator + SQLite masked audit)
  │     ├── /mock/ (fictional HTML citizen portal)
  │     └── /mock/api/* (fictional receipt/status; idempotent)
  └── /api/sessions/{id}/snapshot + /events (live screenshot + SSE events)
          |
          v (internal X-Internal-Key, Docker private network)
    Playwright worker /sessions/*
          |
      isolated BrowserContext
          |
       allowlisted mock host ONLY
```

Each active browser uses one Playwright `BrowserContext`, so cookies and local storage are not shared. Request interception rejects requests off the configured mock host **including subresources**. The non-Docker local runner binds the services to `127.0.0.1`; Docker publishes only the API on `127.0.0.1:8100`. This is **NOT hardened public deployment**.

## API catalogue (working demo)

| Endpoint | Method | Purpose / stage |
|---|---|---|
| `/api/sessions` and `/session` | POST | `{consent:true,profile:{...}}` creates portal browser session |
| `/api/sessions/{id}` | GET | Current state, review digest, repair count, receipt ID |
| `/api/sessions/{id}/fields` | GET | Demo field evidence/source tags |
| `/api/sessions/{id}/snapshot` | GET | Screenshot Base64, ARIA snapshot, human pause flags |
| `/api/sessions/{id}/events` | GET | Server-sent audit events, keepalive heartbeat |
| `/api/sessions/{id}/audit` | GET | Sanitized event history; `after` cursor supported |
| `/api/sessions/{id}/otp` | POST | `{otp}` transient relay (no storage) |
| `/api/sessions/{id}/human` | POST | `{challenge_answer}` user-provided mock challenge |
| `/api/sessions/{id}/fill` | POST | Fill fields; attach synthetic PDF; compare review; hash |
| `/api/sessions/{id}/approve` | POST | `{confirmed:true,review_hash}` one-time signed worker capability then submit |
| `/api/sessions/{id}/inject` and `/session/{id}/inject` | POST | Named chaos script only; demo scope |
| `/api/sessions/{id}/action` | POST | Restricted semantic click/fill/wait; cannot submit or handle secrets |
| `/api/sessions/{id}/poll` | POST | Mock portal status check |
| `/api/sessions/{id}/receipt.pdf` | GET | Labeled synthetic PDF only after successful approval + submission |
| `/api/sessions/{id}` | DELETE | Tear down worker context and remove local record |

Internal worker endpoints require `X-Internal-Key`. Contracts in `contracts/` are **proposed version 1 interfaces**, not yet agreed with teammates; they must be frozen and updated together. They describe profile provenance, extraction, eligibility, doctor, language, events, chaos, vault, actions, browser snapshot. **Vault schema is interface-only, NOT deployed.**

## State machine and review approval

```text
created -> otp_needed -> captcha_needed -> form_ready
 -> [fill + prepared test document] -> [compare actual browser review values]
 -> approval_needed -> [explicit citizen click] -> submitted -> status polling

 chaos expire_session: otp_needed (profile checkpoint remains in API database)
 chaos rename_income: repair saved semantic label via alternate ARIA
 chaos server_failure: retry the failing review transition only
 chaos hide_income: three attempts then human_takeover (fail closed)
```

The worker signs a single-use approval capability bound to worker session ID + review hash + short expiry. **Generic browser actions cannot click Submit**; only the approval endpoint can invoke dedicated worker submit. If portal review content changes, hash verification rejects the capability. The mock portal separately uses an idempotency key to avoid duplicate synthetic receipts.

The worker's name-label repair is a **deterministic demo fallback** and does not constitute general-purpose LLM self-repair or learned skills. A real adapter must capture fingerprints, field-specific postconditions, evaluation metrics and manual approval for high-risk changes.

## Security boundaries and limits

- No real citizen PII, login accounts, bank data or Aadhaar in demo. No real portal is allowlisted.
- No CAPTCHA or face authentication bypass; human explicitly supplies mock challenge answer. No OTP logging or persistence.
- Runtime `APP_MODE != demo` refuses to start. This prevents accidental assumption that demo defaults are production security.
- The browser worker is not publicly exposed; internal header key is sufficient **only** for isolated local demos, not production.
- Missing production requirements: trusted identity and per-session RBAC, separate encrypted vault, managed secrets, object storage, upload malware scanning, legal review, redaction of real portal screenshots, persistent browser checkpoints across process death, approval audit nonrepudiation, tenancy limits, signed job queue, host egress firewall, CSRF, TLS, backup/restore, 30-day artifact cleanup policy + legally mandatory security telemetry retention, account deletion rights, genuine portal agreements.
- Future real portal adapter should be explicitly opt-in after legal review, domain/IP allowlist including redirects and DNS/private range protection, policy-based irreversible action gate and manual credential challenges. Do not ever assume automation rights from public availability.

## Ownership and integration

1. Core teammate consumes `/api/sessions`, `/snapshot`, `/action`, `/events` and human-pause events. Replace `server/app.py`'s thin demo coordinator with LangGraph checkpointer/orchestrator; maintain public endpoints via migration/versioning. A browser context cannot itself survive worker death; orchestration must re-login and replay verified, idempotent steps.
2. Remote teammate sends verified typed profile and document artifacts; change `fill` to accept provenance references and file artifact tokens. Never send raw file bytes in logs.
3. Remote chaos scripts should be checked in and registered by **name** and reviewed; never evaluate arbitrary user-submitted JavaScript. Current endpoint includes six hand-written preapproved mutations.
4. Core teammate controls citizen consent, WhatsApp/voice and strong approval decisions. This demo has a local web consent/approval gate only.
5. Freeze schema versions and use contract tests; assign integration owner for state transitions, approval digest and audit redaction.
