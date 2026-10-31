# Verification record — 31 October 2026

**Current Windows verification supersedes the historical container limits below:** 7 pytest tests pass; full real-HTTP Playwright smoke passes; 35 scenario checks pass (30 synthetic submissions and 5 expected safe handoffs); desktop/mobile dashboard E2E passes. See `E2E_RUN_LOG.md` and `output/local-verification/results.json`. Deployment was deferred by the user. No real government portal submission is claimed.

**Repository:** GradientZero CivicFlow Browser & Product starter.

## Executed in ChatGPT container

| Check | Outcome | Actual evidence |
|---|---|---|
| Python syntax (`compileall`) | PASS | `server`, `browser`, `scripts` compile |
| Browser frontend JS syntax (`node --check`) | PASS | `web/app.js` parses on Node 22 |
| API unit checks | PASS | Demo guardrails, consent, real portal blocked, local endpoints, fake receipt idempotency and status |
| Worker HMAC proof unit | PASS | Session-bound signed capability |
| In-memory Chromium DOM | PASS | Real Playwright Chromium with mocked opaque-origin sessionStorage: OTP, manual challenge, label rename semantic fallback, popup and transient error |
| Worker flow in-memory | PASS | Actual worker `otp`, `human`, `fill` with synthetic PDF, drift, popup, 503 retry, reviewed fields, invalid approval rejection, signed approval, mock receipt |
| **Total tests** | **5 PASS** | `pytest -q` after fixes |
| Actual browser `page.goto(http://127.0.0.1:8100/mock/)` in this container | BLOCKED by environment | Chromium is centrally managed: `/etc/chromium/policies/managed/000_policy_merge.json` includes `URLBlocklist:["*"]` so navigation produces `net::ERR_BLOCKED_BY_ADMINISTRATOR` even on loopback. Not a finding about the repo's allowlist. |
| Complete API ⇄ worker ⇄ browser ⇄ local mock HTTP flow | **NOT VERIFIED** | Cannot navigate to a local URL in managed Chromium here; run `python scripts/smoke.py` on an authorized development machine or CI/Docker host. |
| Docker image build | **NOT VERIFIED** | Docker unavailable in the source environment. |
| Real scholarship portal adapter | **NOT IMPLEMENTED** | No authorized credentials/permissions; official sources only |
| India region deployment | **NOT PERFORMED** | No server access provided |
| Video of complete run | **NOT RECORDED** | Requires full browser runtime |

## Bugs found and fixed during local verification

1. Worker originally read `data-stage` from `body`; mock sets it on `main#main`. Fixed to `#main`.
2. The fictional portal duplicated injected popups across rerenders. Fixed removal of stale dialogs.
3. `crypto.randomUUID()` was unavailable on the opaque-origin in-memory fixture. Added a fixture fallback; normal secure localhost uses `crypto.randomUUID()`.
4. Test cases must restore the income value after mock chaos rerenders the entire form; fixed test and worker fills each field.
5. The 3-attempt human handoff now performs three **actual** scoped attempts, rather than reporting an unperformed count.
6. Session-expiry chaos now actually reopens OTP step, enabling human reauthentication after the checkpoint.

## Required next validation

Run `python scripts/smoke.py` on Docker/normal host, fix any failure and capture a terminal screenshot. Run `python scripts/benchmark.py --runs 5` with each chaos mode. Add screenshot/UI smoke tests and frontend accessibility checks. Verify 2–3 *authorized* real portals separately if possible. Record all metrics in the submission table, and never invent a verified success result.


## Mandatory Mumbai deployment follow-up (31 Oct)

Work-split page 2 makes Mumbai VM deployment + Day-1 portal reachability a **P0 Browser teammate deliverable**; earlier labeling as optional later work was wrong. Added: `compose.vm.yaml`, `deploy/Caddyfile`, `.env.vm.example`, `scripts/deploy_vm.sh`, `scripts/portal_reachability.py`, `docs/DEPLOY_MUMBAI.md`. These provide **deployable scaffolding, not deployment evidence**. No VM/domain/HTTPS certificate has been provisioned by this repo; Docker Compose and live portal access on the VM remain unverified. A local probe URL allowlist unit test is included; actual government portal landing-page and 2–3 E2E flow tests must be run on the VM with authorization.
