# GradientZero / CivicFlow — FORGE '26 Browser & Product Teammate

**Track 1 · Problem 3 — Autonomous Public Service & Bureaucracy Execution Agent.**

This is a **functional demo-oriented starter**, not a finished government portal integration. It includes a Playwright worker, a beautiful local operator console, a fictional scholarship portal, human OTP/challenge pauses, deterministic portal UI-drift repair, explicit submit gate, source-linked fields, audit events, chaos controls, sample receipt and status polling. **Everything is synthetic**: no real scholarship filing, no government affiliation and no actual CAPTCHA solving.

## Start in one command (after Python dependencies)

**Agent/WhatsApp transport wiring:** `docs/CONVERSATION_WIRING.md` documents typed citizen requests/replies, encrypted delivery leases/ACKs, secret-safe verification routing, review decisions, result/status notifications and receipt download. Python/Node clients and `scripts/verify_conversation.py` exercise the exact interface with fake consumers and a real local browser. Core still supplies the actual WhatsApp/model/graph and verifies webhook identities; no external message is sent by this repo.

**General browser/model framework:** read `docs/GENERAL_BROWSER_V2.md` and `docs/INTEGRATION_AUDIT.md`. `/integration/v2/browser` and `clients/general_browser.py` provide page/field discovery, text/ARIA/screenshots/vision bounds, frames/shadow roots/tabs, grounded actions, extraction and provider-neutral decision contracts. No model/agent is bundled. The existing scholarship flow is a separate fixture. Verify with `scripts/verify_general_browser.py`; `scripts/simulate_general.py` creates a synthetic context and prints a read-only workbench URL. Real authentication/submission still needs reviewed adapter policies.

For encrypted local synthetic data, first run `.venv\Scripts\python.exe scripts/configure_local.py` once; the launcher reads private data/local-config.json without printing its keys. Do not overwrite/lose the file or distribute it with source. Read `docs/OPERATIONS_AND_SECURITY.md` before changing keys or enabling signed access. New code includes encrypted artifact references, Python/Node teammate clients, identity revocation/operator grants, bounded streamed requests and backup/restore. `scripts/verify_release.py` exercises complete synthetic wiring; `scripts/package_release.py` builds a source-only handoff archive. A silent local demo can be recorded/checked with `scripts/record_local_demo.py` and `scripts/verify_demo.py`.

**Focused human verification demo:** after starting services, run `.venv\Scripts\python.exe scripts/simulate_handoff.py` and open the printed link. It stands in for a core/WhatsApp message without sending one. For the integration API and boundaries, see `docs/INTEGRATION_V1.md`. The self-contained `.venv\Scripts\python.exe scripts/verify_handoff.py` verifies the mobile page and same-browser continuation on isolated ports.

**Current Windows workspace:** dependencies and Playwright Chromium are installed in `.venv`. Run `start-local.cmd`, then visit http://127.0.0.1:8100. Deployment is deferred at the user's request while local verification is completed. Review now supports editing all five fields and invalidates the previous approval; a lost browser context can reconnect with fresh human login.

To verify the running system: `.venv\Scripts\python.exe scripts/verify_local.py`. This runs five repetitions of seven HTTP scenarios plus a desktop/mobile dashboard flow. Evidence is written to `output/local-verification/`. These are synthetic portal tests, not government applications.

```bash
pip install -r requirements.txt pytest-asyncio
python -m playwright install chromium
python scripts/run_local.py
```

Visit **http://127.0.0.1:8100**. Local runner starts API on 8100 and separate internal browser worker on 8101, both loopback-only. On Linux with Chromium installed, the runner uses `/usr/bin/chromium` if present. Need Python >=3.11. See `.env.example` for settings.

## Docker Compose

```bash
cp .env.example .env
# Randomize INTERNAL_KEY and APP_SIGNING_KEY; do not expose publicly.
docker compose up --build
```

Browse **http://localhost:8100**. Docker is the recommended Windows/macOS development setup. It uses Playwright's official browser image; build may download dependency layers.

## **MANDATORY: Mumbai VM deployment is a Day-1 Browser teammate deliverable**

The source *Forge '26 — GradientZero work split* (page 2) assigns this teammate **Docker-deploying the full web app/API/browser worker to a Mumbai-region VM**, **checking real portal landing pages from the VM on Day 1**, validating **2–3 portal flows five times each**, and **recording a 2–3 minute demo video**. This starter was **NOT** deployed; previous handoff text treating the VM as a later milestone was incorrect.

See **`docs/DEPLOY_MUMBAI.md`**. Included: `compose.vm.yaml`, `deploy/Caddyfile` (HTTPS and password gate for synthetic data only), `.env.vm.example`, `scripts/deploy_vm.sh` and `scripts/portal_reachability.py` (Playwright probe run **inside** the VM's worker container). To deploy after provisioning VM and DNS:

```bash
cp .env.vm.example .env # configure secrets, domain and bcrypt demo password as in deployment guide
bash scripts/deploy_vm.sh
# then execute the browser-worker portal probe and save its JSON results
```

**No cloud instance, DNS, VM credential or deployment proof is included.** Codex/user must actually provision and test them. The provided demo must not be used for real citizen accounts or documents.

## Demo steps

1. Consent and create with prefilled **synthetic** student profile.
2. Enter fictional OTP **246810**, then the manually answered mock challenge **7**.
3. Before filling, try Chaos → **Rename a field**, **Inject a popup**, or **Server error**.
4. Click **Auto-fill and verify review**. Observe actual Chromium screenshot, evidence tags and audit.
5. Only then click **I approve**; the agent submits a **mock** application and returns a mock PDF.
6. Click Check simulated status. Try a second session with Expire login / Hide a field.

## Validation

```bash
python scripts/preflight.py
python -m compileall -q server browser scripts
node --check web/app.js   # optional Node syntax verification
pytest -q
python scripts/smoke.py  # both servers must be running; requires browser URL navigation
python scripts/benchmark.py --runs 5
```

**Important test limit:** Python/JS checks and 5 tests passed in the build environment, but the entire HTTP browser integration was blocked by a managed Chromium URLBlocklist. Smoke and Docker builds have *not* been proven in that environment. See `docs/TEST_REPORT.md` and the Codex handoff for precise next steps.

## Files worth reading

- `AGENTS.md` — Codex entrypoint with full authority to change or rewrite everything.
- `docs/MASTER_HANDOFF.md` — detailed copyable implementation handoff.
- `docs/ARCHITECTURE_AND_INTERFACES.md` — contracts, state machine, API and security boundaries.
- `docs/PORTAL_RESEARCH.md` — official portal shortlist; unknown limits explicitly marked unknown.
- `docs/DEMO_VIDEO_SCRIPT.md` and `docs/SUBMISSION_TEXT_AND_DECK.md` — demo and submission copy.
- `contracts/` — 10 **proposed** (not yet team-frozen) JSON schema files.

## Architecture in 15 seconds

`Static web operator UI ⇄ FastAPI control API / SQLite audit + synthetic portal ⇄ private FastAPI Playwright worker ⇄ isolated Chrome BrowserContext`. API exposes `/docs`, `/health`, `/api/sessions`, SSE events and screenshots. Worker only opens the bundled mock portal, refuses arbitrary URLs and generic Submit clicks. The `approve` API grants a signed, single-use capability tied to portal review hash. OTPs are relayed, never logged or persisted. Errors are fail-closed.

## Production and real portals

**Not supported by this code.** Missing: OIDC, audited portal authorization and terms, verified selectors/forms, real authentication flows, encrypted vault, production artifact privacy, robust 30-day expiry and required security log retention, persisted checkpoints, worker lease routing, real document service, multi-user RBAC, verified India VM deployment, authenticated TLS and genuine site runs. Real OTR may require Aadhaar Face RD and official mobile apps, which the browser must not attempt to emulate.

### Safety

Do not load genuine citizen documents, OTPs, credentials, IDs or real portal URLs in this demo. Do not publish the API to the open internet. Do not claim a mock receipt is government-issued. Authorize actual portal integration and verify terms; pause humans for CAPTCHA, OTP and face authentication.
