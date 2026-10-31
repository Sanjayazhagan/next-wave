# Browser/product release status — 31 October 2026 IST

This is a locally tested browser/product integration release, not a claim of production government application support. APP_MODE=production still refuses startup.

Latest conversation wiring: generation/subject-bound interrupt/reply APIs, typed missing-information questions, encrypted durable delivery queue with leases and ACKs, duplicate-safe response attempts, browser pause enforcement, transient v1 verification routing, correlated review decisions, cleanup/key rotation and Python/Node clients. Approval capture never submits. See CONVERSATION_WIRING.md. Local verification now includes 28 regression tests and the actual browser + fake message-consumer HTTP scenario; real WhatsApp/core/provider integration is not claimed.

## General browser framework correction

The prior release still relied on scholarship-specific navigation/action/extraction. A separate v2 general browser framework is now implemented: structured controls/constraints/text/ARIA/screenshots/vision bounds; permitted frames and shadow roots; navigation, select/check/upload, popup/tab switching, extraction, stale-target checks, readback/provenance and a non-invalidating read-only viewer. Model input/output and a one-step injected ModelPort bridge are provider-neutral. No AI is bundled or claimed to have reasoned. See GENERAL_BROWSER_V2.md and the 17-category INTEGRATION_AUDIT.md for actual implemented replacements and remaining dedicated-adapter boundaries.

The source package's omitted web/ directory was corrected. scripts/verify_package.py now extracts the actual archive, installs its lockfile in a fresh virtual environment and runs packaged human/general-browser HTTP checks, recording its archive hash. The general browser also passes an unrelated multipage fixture with iframe/shadow DOM, tabs, PDF/PNG uploads and a real workbench UI. The regression suite now passes 25 tests. Real auth/challenge/final-submit/receipt adapters remain explicit extension interfaces, not successful default implementations.

| Additional work item | Implemented | Verification |
|---|---|---|
| Encrypted storage | Scoped encrypted profiles/provenance/PDF artifacts, key ring, encrypted backup/restore and offline migration/rotation | Wrong-scope/key, tampering, migration and restore tests |
| Access controls | Signed assertions, owner isolation, token/subject revocation, read-only operator grants, secure-cookie exchange and same-origin mutation checks | Wrong-user, revoked-token, role and cookie/CSRF tests |
| Request hardening | Actual streamed-byte cap, length validation, read timeout, host allowlist and separate request budgets | Chunked overflow before handler, host and rate tests |
| Failure recovery | Durable command IDs/leases, worker/API restart, ambiguous submit reconciliation, stale human-task reconciliation | Process restarts, concurrent/expired-lease and post-commit response-loss tests |
| Human assistance | Focused live image, direct clicks/text/keys, frame/geometry bounds, help/reconnect/expiry, configurable validated return URL | Chromium worker tests, mobile HTTP walkthrough and recorded UI |
| Teammate wiring | Strict schemas/OpenAPI, executable Python/Node clients, encrypted document references and full synthetic integration harness | Six Python runs at concurrency two plus a complete Node flow |
| Operations | Version guard, offline migration, backup restore, scheduled local retention, readiness, aggregate Prometheus metrics, monitor and alert templates | Migration/retention/restore/metrics tests and bounded local benchmark |
| Release packaging | Dependency lock, updated CI/Compose, setup/security guides, allowlisted source archive and actual local demo | Archive hashes/integrity; browser playback/duration check |

## Evidence

The final hardening suite passes 23 tests, with one upstream Starlette/httpx deprecation warning. The mobile HTTP handoff and actual API/worker restart harness pass. The encrypted integration harness passes six concurrent Python flows and a complete Node SDK flow, including durable start/approval replay and event cursors. The dashboard regression covers 35 scenarios (30 mock submissions, five intentional safe handoffs). E2E_RUN_LOG.md and output/ contain the machine evidence.

Five official public pages loaded in local Playwright: NSP, DigiLocker, TN e-Sevai service list, TN welfare and myScheme. This is public-page reachability only, not authenticated adapters or Mumbai evidence. The source archive excludes runtime databases, private local configuration and logs. The 2–3 minute silent video records a real local synthetic flow; playback-check.json records the exact duration.

## Remaining release gates

Actual core/remote/WhatsApp/identity/vault/alert integration, authorized real adapters with observed forms and receipt reconciliation, deployed secret custody and backup policies, production-scale/security review, Docker build and actual Mumbai HTTPS deployment are not completed. No live citizen record or real application should be loaded until those gates are independently verified. Deployment remains deferred by the user. See KNOWN_LIMITATIONS.md for precise scope.

## Handoff

Read TEAM_WIRING_GUIDE.md and OPERATIONS_AND_SECURITY.md. Consume clients/browser_client.py or browser_client.mjs, executable example_core.mjs, contracts/v1 schemas and OpenAPI. The current review instance is loopback port 8600; launcher defaults remain 8100/8101. Browser/product does not implement a competing LangGraph agent or WhatsApp conversation service.
