# Browser and product production-readiness plan

Date: 31 October 2026 IST. Planning document, not an implementation or readiness claim.

## Basis and precedence

Reviewed the handoff README, responsibilities, integration, acceptance, status and submission documents; original five-page team work split and one-page 22-step user flow; repository architecture, contracts and current local evidence.

The original flow permits CAPTCHA screenshot/reply through WhatsApp. The user's newer clarification adds a focused mobile assistance page when direct interaction is necessary. Citizens normally stay in WhatsApp. Our web product contains the assistance page and operator console. Deployment remains deferred by the user; prepare it but do not provision or publish yet. The older master handoff's claim that the saved organizer page proves exact competition wording is superseded by the handoff correction: that snapshot does not establish the full rules.

## Ownership

| Component | Owner | Our responsibility |
|---|---|---|
| Conversation, consent, scheme choice, LangGraph checkpoints, saved skills, approval decisions | Core | Consume authenticated requests, expose observations and enforce execution gates |
| WhatsApp/n8n and Tamil voice replies | Core, with remote language service | Emit human-action requests and completion events; offer a local integration simulator |
| Extraction, compression, eligibility, doctor, chaos module, benchmark, optional watcher | Remote | Validate field/artifact inputs, publish portal constraints, execute reviewed named chaos and return observations |
| Browser contexts, actions, portal adapters, human interaction page, live operator console | Browser/product (us) | Implement and verify |
| Mumbai Compose deployment and actual system recording | Browser/product (us) | Prepare now; deploy after user resumes deployment |

Core is the single business-workflow authority. Browser maintains execution state, locks, event delivery and recovery metadata. Do not create a second production graph or WhatsApp conversation service.

## Citizen journey

1. Core receives the citizen's WhatsApp voice/text, consent, scheme choice and document results.
2. Core starts an authorized browser task with canonical session ID, portal/service ID, consent reference, verified field provenance and scoped document references.
3. Browser logs in, fills approved data and reports observations. OTPs can be relayed transiently through core; never enter them into durable jobs, checkpoints, screenshots, traces or logs.
4. When direct human interaction is required, browser creates an interrupt. Core pauses its graph and sends the assistance link in WhatsApp.
5. The citizen opens a mobile page controlling the existing remote browser context. Prefer a focused viewport around the challenge where the adapter can safely support it. Support pointer/touch/keyboard events, keyboard focus, resizing and coordinate validation. Do not reproduce third-party challenge markup in a separate form.
6. Fall back to the required official-page view or official device flow when focusing is insufficient. Preserve challenge origin/context. Device/face authentication remains on the official app/device.
7. Automation and human control are mutually exclusive. The adapter verifies challenge completion against the live portal before emitting a durable completion event. A Return to WhatsApp action provides navigation; the verified event independently resumes core, so returning is not a correctness requirement.
8. Browser reads back review values and supplies a field diff and protected screenshot. Core obtains explicit approve/edit. Edits invalidate prior approval. Submit requires a valid capability bound to the exact session, portal, scheme, review and expiry.
9. Capture actual receipt/status, pass protected artifacts to core/vault and report observed status. Remote/core owns scheduled notifications.

## Phase 1 — integration contracts and demo boundaries

- Define versioned typed request/response schemas and examples, extending the existing drafts without silently breaking clients. Include canonical IDs, action IDs, expected stage, deadlines, adapter version, provenance, errors and artifact access scopes.
- Agree human-interrupt types: OTP, CAPTCHA, device authentication, assistance and approval. Include interrupt ID, generation, expiry and allowed responses; reject stale responses.
- Define durable browser events with sequence/cursor and authenticated delivery acknowledgement. Handle retries, duplicate callbacks, reconnects and core downtime.
- Provide a local core/WhatsApp message simulator using the same contracts, plus synthetic document and approval fixtures. It stands in for external services, not a replacement implementation of their responsibilities.
- Select demo/real providers explicitly per component. Show active modes in the console and evidence. Missing real dependencies block execution; never fall back to synthetic eligibility, approval, documents or receipts in production.

Acceptance: a teammate can exercise the full browser integration from examples without depending on the dashboard's demo coordinator. Contract tests cover invalid and incompatible payloads.

## Phase 2 — secure human assistance

- Implement mobile task page, interrupt lifecycle and browser-control lease; pause automation until completion/cancellation/expiry.
- Use short-lived task-scoped invitations followed by authenticated session claim. Do not treat possession of a WhatsApp-forwardable URL as sufficient proof of identity for sensitive access. Link previews/GET requests must not consume the task. Revoke on completion, cancellation or session-generation change.
- Prevent reusable URL credentials from leaking into logs/referrers; use secure cookies, CSRF/origin checks, rate limits and authorization on frames, input and events. A link grants only the specified task, never arbitrary browsing or final submission.
- Provide visible expiry/retry, human-help and return-to-conversation paths. Keep operator viewing read-only unless explicitly granted a task.

Acceptance: solve a synthetic interactive challenge from a phone-sized page, observe the same worker context, resume via completion event; reject expired/replayed/wrong-user links, two controllers and stale interrupts. Test direct-interaction and full-page fallbacks. Real challenge compatibility is portal-specific.

## Phase 3 — production browser execution

- Refactor mock-specific logic behind a portal adapter interface: login/relogin, page classification, field mapping, uploads, human challenge detection, review, receipt reconciliation and status observations.
- Add typed click/fill/select/upload/wait/allowlisted navigation with preconditions and postconditions. Protect uploads with owner-bound artifact references, size/type validation and controlled retrieval. Generic actions and assistance controls must not bypass final approval.
- Persist execution/action records and event outbox; serialize actions per session, lease workers, expire idle contexts and limit capacity. Bound retries and backoff; after three failed repair attempts return context to core for human help.
- Core's skill engine decides replay/repair; worker supplies accessible observations and validates actions. Existing deterministic mock repair remains a fixture.
- On browser death notify core, invalidate stale human tasks and approvals, reauthenticate and reconcile portal state. Never promise restoration of a lost in-memory context. After ambiguous submit, inspect existing application/receipt state before any retry.

Acceptance: kill/restart API and worker at login, fill, review and submission boundaries; verify safe recovery and no duplicate submission, alongside concurrent-user isolation and invalid-action tests.

## Phase 4 — verified portal coverage

- Research 4–5 official candidates; classify information/discovery sites separately from application flows. Record actual forms, registration, device dependencies, upload constraints, terms/permission and blockers.
- Start with one authorized flow; expand to the work split's 2–3 validated flows. Implement only observed mappings and agreed permissions.
- Coordinate genuinely eligible consenting applicants. Humans handle authentication. Stop at review if legitimate submission is unavailable; do not submit repeated real applications merely to meet a test count. Use authorized test environments or permissible non-submitting repetitions, labeling their scope accurately.
- Record at least five authorized complete-flow trials per selected portal where possible, preserving the distinction between mock, official public page, authenticated review and actual submission. Report unmet requirements as blockers.

Acceptance: reproducible evidence for each supported adapter and explicit compatibility/blocker records. A homepage load does not prove an adapter works.

## Phase 5 — security and operations

- Integrate core identity/vault with service authentication, rotation and per-session roles. Protect every screenshot, assistance task, document, audit and receipt endpoint; session UUIDs are not authorization.
- Minimize stored browser state; encrypt sensitive artifacts, mask identifiers, disable secret capture and agree a tested retention/deletion policy across browser storage, core vault, external messaging, logs and backups. Implement scheduled cleanup for our artifacts; do not claim all-system 30-day deletion from a browser-only job.
- Add migration tooling, health/readiness, worker-capacity and challenge-timeout metrics, redacted logs, actionable alerts, backup/restore and rollback procedures.
- Pin/test dependencies and images, run CI, bound resource use, restrict egress/redirects, keep worker private and disable chaos outside expressly approved test environments.

Acceptance: wrong-user/role access fails; sensitive fields and OTPs do not leak through evidence; cleanup and restore work; load tests establish supported concurrency and observable failure behavior. This supplements, rather than substitutes for, a release security/privacy review.

## Phase 6 — deployment and release evidence

When deployment is resumed: verify Docker build, deploy on an actual Mumbai VM with HTTPS, access control and persistent services. Verify region and external dashboard/human-assistance access. Probe official public pages from that worker's Chromium. Integrate core/remote services and complete a WhatsApp-to-human-assistance-to-review/approval-to-result journey.

Produce the required 2–3 minute recording, six-slide deck, setup/architecture docs and submission copy with measured claims. Keep mock evidence separate. Independent browser demo readiness, integration readiness and production readiness are different milestones.

## Immediate execution order

1. Versioned contracts and demo dependency simulator.
2. Human-assistance page and interrupt/event lifecycle.
3. Worker isolation, approval/reconciliation and crash recovery.
4. Authorized portal research/first adapter, then expansion.
5. Actual teammate integrations, security and operational validation.
6. Mumbai deployment and release artifacts after deployment is resumed.

Security is implemented in each phase, not postponed to phase 5.

## Inputs the user/team must supply

- Core/remote contact or shared repository/API examples to agree contracts and connect actual services. No claim that drafts are team-approved.
- Initial portal/service choice, authorization and consenting eligible applicant access; accounts/OTP/device steps remain under the applicant's control.
- Chosen identity/access arrangement with core; secrets supplied through secure configuration, not chat.
- Mumbai host/access, domain and deployment resumption when ready.
- Agreement on operational ownership, retention and release acceptance for the complete product.

We can implement phases 1–3 and local operational scaffolding without these external services, using labeled fixtures. Live integrations, real portal coverage and complete production readiness remain gated on actual access and verification.
