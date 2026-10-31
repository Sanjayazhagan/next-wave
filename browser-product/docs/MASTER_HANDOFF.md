# MASTER HANDOFF — GRADIENTZERO / FORGE '26

## Current chat update — 31 October 2026 IST

See RELEASE_STATUS.md and TEAM_WIRING_GUIDE.md for the latest implementation, versioned core APIs/client, interactive human control, optional identity, provenance/doc inputs, action replay/reconciliation, retention/backup and new evidence. These supersede historical status below. The latest full local check has 14 passing tests, 35 HTTP scenarios and mobile/restart E2E; official landing-page reachability is local only. Production, real authenticated adapters and deployment are not verified.

The user deferred deployment and requested local verification first. This supersedes the older immediate deployment priority below. See `CHANGELOG.md`, `KNOWN_LIMITATIONS.md` and `E2E_RUN_LOG.md` for current changes and evidence. Windows dependencies are installed in `.venv`; use `start-local.cmd`. Added `/api/sessions/{id}/edit` and `/resume`, plus private worker `/sessions/{id}/edit`. Editing invalidates approval; browser recovery requires human login again. All flows remain synthetic and teammate integrations remain pending.
## For Codex / autonomous coding agents / the on-campus Browser & Product teammate

**Date:** 31 October 2026 · **Track:** 1, Problem 3 · **Product:** CivicFlow / Team GradientZero · **Repo:** `gradientzero-browser/` · **Mode:** demo-only until production security + legal approvals.

## 0. START HERE — THE MOST IMPORTANT INSTRUCTIONS

**YOU ARE FULLY AUTHORIZED TO CHANGE EVERYTHING IN THIS REPOSITORY.**

This archive is **boilerplate, not an architecture contract**. You (Codex) have complete permission to **refactor, delete, replace, ignore, redesign, migrate, or entirely rewrite the codebase from scratch** if any implementation, dependency, structure, UI, test, deployment choice or document is inadequate. You are not required to maintain this author’s framework or code style. You can adopt FastAPI, TS/Node, Next.js, Vite, LangGraph integration or a completely different design. Optimize for a functioning, demonstrable, secure, reliable hackathon submission. Decide independently, test changes, and record rationale in changelog. You may follow **newer implementation instructions given by the user in chat**, even if they conflict with this proposal or boilerplate. The code here is a starting point, not a restriction.

**Interpretation/precedence:** follow the newest explicit user objectives and instructions; **mandatory security, authorization and compliance guardrails cannot be waived**; then this handoff for gaps; then current code. If a user directs a change that conflicts with a mandatory safety/compliance boundary, implement the nearest safe alternative and explain the difference. If you change an interface, version it and update all caller modules, tests and docs in the same commit.

Do the work directly: inspect repository, run code, write tests, fix issues, improve visuals, and deliver artifacts. **Do not report successful deployment, a working live government portal, or passing browser E2E unless you actually verified it.** Keep reproducible evidence of test results.

**Non-negotiable project intent:** a citizen initiates a public service request in Tamil; core agent checks deterministic eligibility, verifies/normalizes documents, uses a browser worker to fill legacy public portals, pauses for actual OTP/CAPTCHA/Aadhaar device steps, retries/replans upon UI drift, verifies review fields against evidence, gets explicit citizen approval before irreversible submission, returns a receipt, and tracks status with an audit trail. The browser teammate owns the portal execution and product UI; mock demos must not be misrepresented as real applications.

## 1. Primary sources, problem exactness and work split

The attached *NxtWave — Revolutionizing the Job Market* saved hackathon page identifies **Theme 1 / Problem Spectrum #3: “Autonomous Public Service & Bureaucracy Execution Agent”**. It describes an autonomous web/browser agent using browser-use/Playwright, ingesting a citizen’s background and requested service, navigating legacy non-API public portals, populating forms, handling obstacles, and returning completed tracking receipts. This is the official task description; the scholarship specialization is the **team's chosen demonstration**, not a universal scope restriction.

The uploaded *Forge '26 — GradientZero work split*, p.2, assigns this teammate **the browser, real portals, web app, server, CAPTCHA/error detection, login/re-login, 2–3 portal flows, chaos injection, India-region deployment, and demo recording**. Its p.4 requires interfaces to be frozen before parallel work. It expects a shortlist of 4–5 portals after four hours and five successful E2E runs per chosen portal. The document places **LangGraph, graph checkpoints, approval interrupt, encrypted vault, skill library, n8n/WhatsApp** under the core teammate and **document extraction, file compression, eligibility, doctor, chaos/benchmark/status watcher** under the remote teammate. Integrate, don't silently take over teammates’ areas.

The uploaded *495.pdf*, one-page user flow, lists: Tamil voice request → informed consent → eligibility first → documents and doctor → portal login (human OTP/face-auth) → accessible/visual browser actions with live feed → one-step skill repair and checkpoint after outages → CAPTCHA human → review/approval (edit loop) → receipt → tracked status. It states OTPs never stored, identifiers masked, personal data auto-deleted after 30 days as product goal, and no CAPTCHA/OTP bypass.

**Original source PDFs are not duplicated in this archive**. The original uploaded documents should remain the source of truth when Codex has access to them.

## 2. What exists in this ZIP (actually implemented)

- `server/app.py`: FastAPI **demo** API, SQLite database, local/mock web portal, consent, profile, per-field provenance (fixture), guarded approval, signed worker capability, synthetic PDF receipt, status check, masked audit, SSE, named chaos, session delete.
- `browser/worker.py`: separate FastAPI internal Playwright worker, browser-context-per-session, screenshots and ARIA snapshots, semantic fill/click, human OTP and challenge relay, PDF attachment, alternate semantic locator self-repair for known demo label drift, popup dismissal, retry on simulated transient error, fail-closed helper state, confined URL allowlist, irreversible-submit authorization proof.
- `web/index.html`, `web/app.css`, `web/app.js`: a real static responsive console: streaming (periodically refreshed JPEG) browser, state machine, provenance, audit trail, named chaos buttons, consent, simulated OTP/challenge, review approval, receipt and status.
- `web/mock.html`: **fictional** scholarship portal. OTP fixture `246810`; mock human arithmetic question `3 + 4`; five required test fields; simulated PDF requirement; review, idempotent fake submission and receipt.
- `contracts/*.json`: **proposed** JSON Schemas; core/remote teammates must jointly freeze, version and validate.
- `tests/`: API guardrails and browser in-memory DOM interaction tests.
- `scripts/`: local runner, preflight, smoke test and benchmark; `Dockerfile`/`compose.yaml` for reproducible local demo.
- `docs/`: architecture/contracts, **mandatory Mumbai deployment guide**, portal desk research, video script, submission copy, current test report and this handoff.

### Repo map

```text
gradientzero-browser/
├── AGENTS.md                    # concise Codex entry instructions
├── README.md                    # setup and limitations
├── .env.example
├── Dockerfile
├── compose.yaml
├── requirements.txt
├── pyproject.toml
├── browser/
│   ├── __init__.py
│   └── worker.py              # private FastAPI+Playwright service
├── server/
│   ├── __init__.py
│   └── app.py                 # public local demo API, mock portal, SSE, DB
├── web/
│   ├── index.html             # operator console
│   ├── app.css
│   ├── app.js
│   └── mock.html              # synthetic scholarship portal
├── contracts/                 # ten proposed JSON schemas
├── docs/
│   ├── MASTER_HANDOFF.md
│   ├── ARCHITECTURE_AND_INTERFACES.md
│   ├── PORTAL_RESEARCH.md
│   ├── DEMO_VIDEO_SCRIPT.md
│   ├── SUBMISSION_TEXT_AND_DECK.md
│   └── TEST_REPORT.md
├── scripts/
│   ├── run_local.py
│   ├── preflight.py
│   ├── smoke.py
│   └── benchmark.py
├── tests/
│   ├── test_api.py
│   └── test_browser_inmemory.py
└── .github/workflows/ci.yml
```

## 3. Install and run (choose ONE path)

**Local Python, Linux with Chromium**

```bash
cd gradientzero-browser
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest-asyncio
python -m playwright install chromium   # if system chromium absent
cp .env.example .env                    # optional; local runner sets defaults
python scripts/preflight.py
python scripts/run_local.py
# browse http://127.0.0.1:8100 (same-origin API and UI)
# docs   http://127.0.0.1:8100/docs
```

For Windows with Docker Desktop, use Compose rather than `/usr/bin/chromium`. **Managed browsers with URLBlocklist may refuse all URLs**; use an unrestricted authorized Playwright runtime / Docker, don't alter enterprise policies.

**Docker Compose (recommended on normal local machine)**

```bash
cp .env.example .env
# Change INTERNAL_KEY and APP_SIGNING_KEY to long random secrets
# In Docker Compose, mock/worker URLs are configured internally; don't use the local defaults.
docker compose up --build
# visit http://localhost:8100
# all private worker traffic remains on the compose network
```

Basic verification:

```bash
python -m compileall -q server browser scripts
node --check web/app.js
pytest -q
python scripts/smoke.py   # with app+worker running; requires actual browser navigation
python scripts/benchmark.py --runs 5
```

### Known initial verification status

This package was assembled in the ChatGPT execution container. **Python compilation, JS syntax and five local tests passed**; the DOM Playwright test used in-memory HTML and real Chromium. **The complete HTTP browser E2E could not be run in this host** because its centrally managed Chrome policy sets `URLBlocklist:["*"]`, causing `net::ERR_BLOCKED_BY_ADMINISTRATOR` on loopback URLs. The code is therefore **NOT claimed proven to complete the full browser-to-server flow**; rerun `scripts/smoke.py` in Docker/CI/your machine and fix any integration bug. Docker isn't installed in the current research container. The 2–3 live portal runs and **mandatory Day-1 Mumbai deployment** also remain undone; see `docs/DEPLOY_MUMBAI.md` for new VM provisioning, protected demo Compose overlay and browser-worker landing-page probe. See `docs/TEST_REPORT.md`.

## 4. Operator demo — exact actions

1. Open `http://127.0.0.1:8100`; review the fictional-portal disclaimer.
2. Enter **synthetic** profile (provided defaults) and check consent. Create session.
3. The live screenshot should show the fictional portal's OTP page. Enter `246810` (mock fixture), click verify.
4. Enter manual challenge answer `7` and continue. The browser moves to the application page.
5. **Before** filling, click `Rename a field`, `Inject a popup` and/or `Server error` in Resilience Lab.
6. Click `Auto-fill and verify review`. The worker fills 5 fields and attaches synthetic PDF, repairs the known label change/popup, retries transient failure, and checks the actual review values.
7. The UI goes to `Awaiting approval`, shows field sources and audit events. Click **I approve** to authorize the mock submit.
8. Mock receipt appears; click `Check simulated application status` and `Download mock receipt PDF`.
9. A second demo shows `Expire login` before filling, then user re-enters the **mock** OTP and challenge; the coordinator preserves profile data. A third shows `Hide a field`, triggering `human_takeover` instead of forging values.

**Do not say “we filed a real scholarship” if you only used the mock.** Show official portal research as a separate prospective integration.

## 5. Minimal API payloads and contracts

Public API prefix `/api`. `POST /session` is a compatibility alias, as is `POST /session/{id}/inject`.

```http
POST /api/sessions
Content-Type: application/json

{"consent":true,"portal":"mock-scholarship","profile":{"student_name":"Kavya Demo","course":"B.Tech","income":"120000","state":"Tamil Nadu","category":"BC"}}
```

```http
POST /api/sessions/{id}/otp       {"otp":"246810"}
POST /api/sessions/{id}/human     {"challenge_answer":"7"}
POST /api/sessions/{id}/inject    {"script_name":"rename_income","options":{}}
POST /api/sessions/{id}/fill      {}
GET  /api/sessions/{id}
POST /api/sessions/{id}/approve   {"confirmed":true,"review_hash":"<digest from GET>"}
POST /api/sessions/{id}/poll      {}
GET  /api/sessions/{id}/receipt.pdf
GET  /api/sessions/{id}/events    (SSE)
```

Worker API includes `POST /sessions`, `GET /sessions/{id}/snapshot`, `POST /sessions/{id}/{otp,human,fill,inject,submit,action}`, `DELETE /sessions/{id}`; all require `X-Internal-Key` and never publish its port outside Docker. Worker action accepts only label/role semantic locators, blocks submission and authentication fields. The dedicated `submit` endpoint checks signed, expiring review-hash capability and one-time use. **This is a functional demo security feature, not production authorization**; a real identity system must bind approval to authenticated user + explicit intent and use atomic durable approval records.

### Inter-team data contract

- `profile.schema.json` — remote extraction and verified citizen profile, `fields.<name>.{value,source_document,source_ref,confidence}`.
- `extracted-document.schema.json` — extractor output.
- `eligibility.schema.json` — scheme decision with cited clauses; rule engine deterministic; browser MUST NOT claim eligibility.
- `doctor.schema.json` — mismatches, risk score, allow/block.
- `agent-event.schema.json` — core-to-web/n8n event bus.
- `browser-snapshot.schema.json` and `browser-action.schema.json` — snapshot/action boundary.
- `chaos-inject.schema.json` — script name and options; remote teammate contributes reviewed scripts.
- `language.schema.json` — STT/translation/TTS proposed shared payload.
- `vault.schema.json` — **interface-only**, intended to be owned/implemented by core teammate.

**Important:** These schemas are draft proposals, not frozen externally. Hold a 15-minute contract sync, agree exact version, add schema validation CI, and update core and remote teammates.

## 6. Critical tests for Codex to implement and run

First priority in a normal runtime: `python scripts/smoke.py`, and **fix** every failure. Then:

| Test | Expected |
|---|---|
| Start without consent | HTTP 400, no browser created |
| Arbitrary real-portal navigation | HTTP 403/400; no network request |
| OTP blank/wrong | stays `otp_needed`; no OTP in DB/audit |
| CAPTCHA/challenge wrong | stays human pause; no automatic answer |
| Semantic locator drift | alternate accessible label fills; repair count increments |
| Popup | modal dismissed only if approved/test fixture |
| Transient failure | retries same safe step, not restarting application |
| Hidden required field | no fabricated values; human takeover after 3 failed retries |
| Expired login | returns to human OTP; profile checkpoint intact |
| Review mismatch | blocks approval; fields and profile must match |
| Submit via generic action | HTTP 403 |
| Submit without approval | HTTP 403 |
| Approve with wrong review hash | HTTP 409 |
| Submit with old/used capability | HTTP 403 |
| Second synthetic submission | idempotency returns same receipt |
| Browser contexts of two sessions | cookies/sessionStorage cannot cross |
| SSE | event types, data masking, reconnect and frame cadence |
| Unknown chaos script | HTTP 400; no eval of user JS |
| Status before submission | HTTP 409 |
| Delete session | browser context destroyed, no DB record |
| Browser worker restart | old browser lost; **requires added core checkpoint/re-login solution** |

For real portals, only use authorized accounts. Record **five complete runs for each of the 2–3 selected portal adapters**, field/document constraints, session-expiry behavior and inability to complete some human-controlled steps unattended. Do not claim those are finished now.

## 7. Known gaps and next milestones (prioritized)

**P0 — required before submission demo**

1. **Day-1 VM deployment is mandatory (work split p.2).** Provision Mumbai-region host, Docker Compose deploy API + browser worker + dashboard behind HTTPS/password, confirm browser feed from VM, and record browser-worker reachability of real portal landing pages from the VM. Read `docs/DEPLOY_MUMBAI.md`. This is not yet completed. In parallel, get real Chromium network navigation working on your machine/CI; run smoke 5x; fix browser/worker/UI timing and ensure no incidental duplicate receipts.
2. Agree frozen contracts and bind the on-campus core agent. Choose one orchestrator owner; replace demo coordinator once real LangGraph ready.
3. Manually inspect 4–5 real portals for credentials, face-auth, CAPTCHA, upload limits, terms and consent; pick 2–3 only if allowed and testable. If authorization absent, **clearly disclose** and demonstrate on mock.
4. Implement real portal-specific adapters with explicit allowed host/policy, safe navigation, field postconditions and human checkpoints. Do not invent selectors or bypass defenses.
5. Test each of the 2–3 **authorized real portal flows five times** and keep timestamped evidence; synthetic mock tests must be separately labeled. Rehearse on the deployed system, record 2–3 min video, freeze before deadline.

**P1 — meaningful reliability upgrades**

6. Session persistence across worker crashes: use explicit worker ID lease + DB checkpoints, safe re-login and replay from field-level idempotent actions; no promise of browser context resurrection.
7. Save portal skill candidates, fingerprints, successful replay and repairs in a versioned store, under core teammate's ownership; compare against deterministic baseline with blind test changes.
8. Implement authenticated helper takeover and browser session delegation; never give unverified operators access.
9. Real file upload preparation endpoint with types/size/resolution constraints per **verified portal**, malware scanning, encrypted artifact handling and per-field provenance, plus image redaction.
10. Build integration tests: browser-context isolation, redirect / private IP SSRF protection, approval race tests, auth token replay, screenshot privacy, role checks.

**P2 — production only after governance**

11. Campus OIDC, hardened RBAC, revocation, audit append-only / legal retention, CSRF, encryption/KMS, signed artifact URLs, Indian region hosting, central logging, backups and policy approvals.
12. WhatsApp/n8n + Tamil ASR/TTS with explicit user consent and tested API keys; no production mock OTP fixtures.
13. Approved government portal integration only, with documented portal owner permission/terms; no automated OTP or CAPTCHA solving.
14. For eventual **real citizen / production** deployment only: replace demo auth with OIDC/RBAC and audited legal/privacy/security controls. **Unprotected public exposure of the demo is forbidden**, but a private HTTPS + password-gated synthetic demonstration on the Mumbai VM is a required Day-1 deliverable. See `docs/DEPLOY_MUMBAI.md`.

## 8. Timeline for on-campus browser teammate

The work-split PDF schedules: by hour 2 contracts; by hour 12 first portal path; by hour 24 full web and WhatsApp loop; hour 34 chaos/self-repair; hour 44 feature freeze, video/deck/README. Deadline **Sunday 1 November 2026** (work split calls for submitting by 10 PM; platform cutoff stated as 11:59 PM). Track commitments realistically: testing real portals requires authorized accounts; prioritize mock demonstrability rather than false claims.

Recommended order: contract freeze → **provision/deploy Mumbai VM on Day 1 and prove real portal landing-page reachability from the worker** → smoke/bug-fix → authorized portal flow(s) (five runs each) or openly labeled mock if access is blocked → run chaos cases and record metrics → integrate core pause/resume → stage UI review and audit → record 2–3 minute video from VM → freeze → submit by earlier internal deadline.

## 9. External technical research references

- [Official NSP page](https://scholarships.gov.in/home) and [OTR information](https://scholarships.gov.in/otrapplication/), checked in deep research 31 Oct 2026.
- [Tamil Nadu e-Sevai institutional services](https://tnesevai.tn.gov.in/Pages/EsevaiServiceListInstitution.aspx), [BC/MBC scholarship information](https://bcmbcmw.tn.gov.in/welfschemes.htm).
- [Playwright browser contexts](https://playwright.dev/python/docs/browser-contexts), [semantic locators](https://playwright.dev/python/docs/locators), [ARIA snapshot API](https://playwright.dev/python/docs/api/class-locator), [traces](https://playwright.dev/python/docs/trace-viewer).
- [FastAPI deployment](https://fastapi.tiangolo.com/deployment/docker/), [Docker Compose](https://docs.docker.com/compose/how-tos/production/).
- [OWASP ASVS 5](https://asvs.owasp.org/), [Indian DPDP Act](https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse), [CERT-In 2022 directions](https://cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf).

**Do not infer government endorsement, robot permission or actual site compatibility from these links.** Verify current official terms and user authorization for every action.

## 10. Final acceptance gate and reporting format

Before calling the feature complete, report a table with `feature / implementation path / proof of test / exact result / remaining risk`. Mandatory checks: startup + full browser navigation; error recovery; at least one hard human pause; 5 repeat runs; screenshots and audit; real source tags; no unapproved submission; receipt; status; demo video. Separate *implemented*, *verified*, *prototype only*, and *blocked*. Keep public demo separate from real citizen workflows.

**Final reminder to Codex:** Your authority to rewrite is broad and explicit. Preserve the user’s objectives and the mandatory human approval, OTP/CAPTCHA/device-auth, privacy, provenance, and legal requirements. Build the best solution you can verify. Do not treat this boilerplate as sacred.


## 10. Source-corrected mandatory deployment addendum (31 Oct 2026)

**READ FIRST: `docs/DEPLOY_MUMBAI.md`.** The work-split p.2 assigns the Browser teammate physical **Mumbai-region VM deployment with Playwright browser worker** and demands verification **on day 1** that the candidate government portals load *from that VM*. It also assigns server ownership and video capture, plus **2–3 real portal flows with five complete runs each**. An earlier draft incorrectly grouped VM deployment as a P2/postponable activity; that has been corrected. This starter adds a Compose TLS/password-gated overlay, a VM operator deployment script and a read-only Chromium reachability probe. **No cloud deployment has actually occurred; never claim one.** Missing VM credentials/DNS/institutional permission are user/team prerequisites, not reasons to mark task done.
