# Highest-priority latest scope — 31 October 2026 (supersedes old deferral notes)

**Do NOT build a second agent or treat the demo as the product.**
Main `Sanjayazhagan/next-wave` runs the actual LangGraph, model, chat channels,
consent/approval and vault. This feature branch owns the live browser execution
and product. Read `docs/MAIN_AGENT_INTEGRATION.md`,
`docs/AGENTIC_INTEGRATION_RELEASE.md`, and
`docs/WORKER_HANDOFF_TO_CODEX.md` and `docs/BRIDGE_FIX_HANDOFF_OCT31.md` FIRST. Browser API:
`/core-browser/session` → private Playwright `/core/session`. Old main patch was removed because the teammate's latest branch changed.
Use minimal, reviewed changes against current main; do NOT replace nodes.py.

**Deployment is now explicitly requested again.** Prior messages below saying
"deployment deferred" are stale. Actual Mumbai VM deployment and real-site
verification remain uncompleted and are P0. Never report them as done.

`APP_MODE=integrated` activates operator-reviewed portal navigation; see
`compose.integrated.yaml` and signed auth requirements. This is not a claim
of production certification. OTP/CAPTCHA/security controls remain human-only,
last submit requires fresh citizen approval, and real portal authorizations
must be established. The main agent decides which actions to take.

---

# Codex agent instructions — GradientZero Browser & Product

## Latest user scope (31 October 2026 IST)

Conversation wiring pass: server/conversation_bridge.py and Python/Node ConversationClient expose typed questions/replies, encrypted outbox leases/ACKs, pause and generation/subject gates, transient v1 verification routing, review decision capture (not submit), receipt/status notifications and authenticated receipt download. Read docs/CONVERSATION_WIRING.md. No actual WhatsApp provider/webhook/model/graph is implemented here. Test baseline: 28 tests plus scripts/verify_conversation.py with real HTTP/browser and fake consumers; secrets must not enter durable graph/log/message payloads. Generic v2 auth/device/receipt still requires reviewed adapter implementations and explicitly fails when absent.

Newest browser framework: v2 general observations/actions are separate from the scholarship fixture. Read docs/INTEGRATION_AUDIT.md and docs/GENERAL_BROWSER_V2.md before claiming general AI capabilities. browser/protocol.py defines ModelPort/ModelDecision; no model/agent is bundled. GeneralBrowserClient and scripts/verify_general_browser.py exercise unrelated multipage controls, frames/shadow DOM, popups/tabs, PDF/image artifacts, extraction, stale guards and a non-invalidating viewer. Dedicated auth/challenge-completion/final-submit/receipt adapters remain explicit unavailable interfaces, not successful stubs. Default origin policy stays local, generic writes/final submit are blocked and deployment remains deferred.

Newest pass: encrypted profiles/provenance/artifacts, offline migration/rotation and encrypted backup/restore, access revocation/operator grants, cookie/CSRF, actual streamed-body limits, broader budgets/hosts, human-help/reconnect/expiry, Python/Node examples, metrics/alerts and source packaging. Read docs/OPERATIONS_AND_SECURITY.md. Private data/local-config.json is generated and ignored; never print or package it. Test baseline is 23 passing tests plus mobile/restart/concurrent wiring and 35-scenario dashboard checks. The source archive is built via scripts/package_release.py; the actual silent local recording is output/demo/civicflow-local-demo.webm. Do not infer production or real-portal support from these synthetic artifacts.

Latest implementation: read docs/RELEASE_STATUS.md and docs/TEAM_WIRING_GUIDE.md. Core wiring lives under /integration/v1, clients/browser_client.py and contracts/v1. Signed identity is optional for isolated integration testing; APP_MODE=production is still intentionally unsupported. Do not claim real adapter support or production readiness from local synthetic tests. Tests include scripts/verify_handoff.py and scripts/verify_resilience.py. The current review instance uses ports 8600/8601; older instances may also be present.

The user explicitly deferred deployment: verify everything locally first. Do not provision or deploy until requested again. Use `.venv/Scripts/python.exe` on this Windows workspace; the system `python` alias is unusable. Start with `start-local.cmd`. Run `scripts/verify_local.py` against the running services for actual HTTP and dashboard browser checks. All application runs remain synthetic.

READ `docs/MASTER_HANDOFF.md` FIRST. It is the full team brief, source traceability, instructions, test and integration plan. The latest explicit user directions in chat are the primary project goals, subject to mandatory security, authorization and compliance rules.

**Full rewrite authority:** You have unrestricted permission to refactor, replace, delete, ignore or completely rebuild this boilerplate from scratch. You may choose a different language, architecture, components or tools. You need not preserve current files beyond useful requirements and properly versioned external contracts. Make reasoned decisions, perform actual work, test, improve, and deliver. Any newer explicit implementation directions from the user may supersede this boilerplate/handoff, but must not waive mandatory human approvals, OTP/CAPTCHA/device-auth controls, privacy, or portal authorization.

**MANDATORY OWNER DELIVERABLE — DAY-1 MUMBAI VM DEPLOYMENT:** The work-split PDF p.2 expressly assigns the Browser teammate Docker Compose deployment of the entire web app, server and Playwright worker on a Mumbai-region VM, with Day-1 browser-worker checks that actual candidate portals load from that server. This is **P0**, not P2. Read `docs/DEPLOY_MUMBAI.md`; build/verify from the VM, capture reachability evidence, confirm password-gated HTTPS + live browser, and record the 2–3-minute demo video. If no VM/cloud credentials/domain are available, identify the exact blocker and do all local/infra preparation first; never invent deployment success. Requirement also includes 2–3 authorized portal flows each tested end-to-end five times; mock tests are not substitutes and must be labeled.

Do NOT claim real-portal automation is implemented. All currently implemented flows are fictional mock demo only. The environment that generated this archive has Chromium enterprise URLBlocklist and couldn't verify full HTTP navigation; run integration tests on your own host/container first.

Order: `README.md` → `docs/MASTER_HANDOFF.md` → `docs/ARCHITECTURE_AND_INTERFACES.md` → preflight / unit / smoke → implement missing requirements → rerun tests → document facts. Maintain honest distinction between real work and simulated workflow.


## Dynamic public URL navigation (31 Oct 2026)
- Read `docs/DYNAMIC_PUBLIC_WEB.md` before editing security or browser routing.
- `BROWSER_NAVIGATION_MODE=public-web` accepts consent-backed HTTPS URLs at runtime in both `/core-browser/session` and `/integration/v2/browser/contexts`; no manual registry entry is needed per website.
- Do not allow access to private networks, localhost, cloud metadata, embedded credentials or arbitrary ports. DNS and URL validation MUST remain enabled. These checks do not replace network egress isolation for untrusted browsing.
- Keep the existing `main` LangGraph implementation intact. Its current `open(portal_id)` can continue on registered portals; its owner can optionally adapt it to send `url` and `consent_ref`.
- Never bypass OTP/CAPTCHA or irreversible-submit gates; do not claim complete real portal support.
