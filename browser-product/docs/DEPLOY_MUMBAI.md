# Mandatory Day-1 Mumbai deployment — Browser & Product teammate

**Source of truth:** *Forge '26 — GradientZero work split*, p.2, items 1–8 and Browser deliverables. The Browser teammate **owns the server, Docker deployment, real-portal reachability check, web app and demo recording**. Deployment is **P0 on Day 1**, not a later production enhancement. The current starter has **not** been deployed to any VM; it contains ONLY fictional demo portal execution. These are instructions, **not deployment evidence**.

## Mandatory acceptance / evidence

1. Obtain an Indian Mumbai cloud VM (e.g. AWS EC2 region `ap-south-1`). Record actual instance region, public IP, VM operating system and instance size (avoid saving credentials). **Do not write “Mumbai deployed” without cloud console/CLI proof**.
2. Deploy both **API / dashboard** and **Playwright browser worker** with Docker Compose, private worker-only port, persistent demo DB and an HTTPS endpoint protected by username/password. Record successful `docker compose ps`, `/health`, and screenshot of logged-in dashboard with active browser stream.
3. **During Day 1, check at least 4–5 candidate government portals from the Mumbai worker's own Chromium instance.** Run the provided read-only public landing-page probe for four targets; manually add a fifth candidate after verifying the official URL. Keep JSON output and screenshot/notes. A loaded homepage does NOT prove a portal login/form can be automated.
4. Inspect and shortlist **2–3 permitted, accessible portal flows**. For each, record fields, documents, upload limits, registration/OTR requirements, manual OTP/CAPTCHA/device-auth steps, session expiry and terms. Work with core teammate on checkpoints. Target **five actual E2E runs for each selected portal**; separately report inability to obtain permission/account if applicable rather than counting synthetic runs as real portal runs.
5. Demonstrate user-friendly dashboard: live browser screenshots, stage/agent reasoning, per-field source, audit trail, and chaos button. Remote teammate's chaos script must run through `POST /session/{id}/inject`; coordinate contract compatibility.
6. Record a real **2–3 minute video** using the running deployed system. Show intentional failures, recovery, citizen review approval, mock application/receipt where applicable; **label mock results**. Video and test evidence are required deliverables.

## Infrastructure sketch

```
Trusted teammate/judge browser
       |
       v
https://demo.<team-domain> (DNS -> Mumbai VM public IP)
       |
       v
Caddy TLS + Basic Auth (ports 80,443)
       |
       v
Compose internal network
  API/FastAPI :8000  -----> Worker/Playwright :8101 (NOT published)
     |                           |
  synthetic portal          Headless Chromium
     |
 Persistent Docker volume (demo SQLite)
```

The base `compose.yaml` binds the API's debug port only to `127.0.0.1:8100` on the VM. The additional `compose.vm.yaml` adds password-gated TLS proxy. This is ONLY a **synthetic demo**; Basic Auth alone is NOT sufficient authentication for actual citizen records or real government applications. Use only seeded fictional data here.

## A. Provision Mumbai VM (operator action required)

- Select cloud location **Mumbai** explicitly; on AWS this is **`ap-south-1`** (NOT Singapore/Bangalore/Delhi). Record proof of region from the provider console.
- Suggested starting capacity for one Chromium stream: Ubuntu 24.04, >=2 vCPU, >=4 GB RAM (8 GB preferable for simultaneous sessions), >=20 GB disk. Adjust from measurements.
- Install Docker Engine and Compose plugin from official provider documentation; enable/restart Docker and grant the deployment user only the necessary permissions.
- Firewall/security group: SSH 22 **only from your IP**, TCP 80 and 443 for TLS and demonstration audience. **Never publish 8000, 8100, 8101, SQLite, or the Docker socket**. Restrict VM egress as required by institutional policy; government portal outbound HTTPS 443 must work.
- Use a DNS A record pointing `DEMO_HOST` to the VM public IP. A real domain/DNS and accessible 80/443 are required for Caddy automatic HTTPS. Do not use an `example` name and expect TLS issuance.
- Transfer only this code and **synthetic** fixtures. Never copy government credentials, real Aadhaar, portal OTP, certificate scans or banking data into this prototype.

## B. Configure

From the repo root on the VM:

```bash
cp .env.vm.example .env
openssl rand -hex 32  # INTERNAL_KEY: paste the result into .env
openssl rand -hex 32  # APP_SIGNING_KEY: generate a DIFFERENT result
# Generate an interactive bcrypt password hash (no plaintext in .env):
docker run --rm -it caddy:2.10 caddy hash-password
# Enter your chosen password when prompted, copy hash into .env.
# Surround hash with SINGLE quotes: DEMO_PASSWORD_HASH='$2a$...'
chmod 600 .env
# Edit DEMO_HOST, ACME_EMAIL, DEMO_USER, DEMO_PASSWORD_HASH and keys.
```

**Privacy:** Secure the plaintext demo password in your own password manager; never commit it. Browser Basic Auth may cache it. Do not publicly share demo access without understanding this demo's limitations. Use an identity-aware access proxy for stronger access controls.

## C. Launch and prove actual deployment

```bash
bash scripts/deploy_vm.sh
# or, manually:
docker compose --env-file .env -f compose.yaml -f compose.vm.yaml up -d --build
docker compose --env-file .env -f compose.yaml -f compose.vm.yaml ps
docker compose --env-file .env -f compose.yaml -f compose.vm.yaml logs --tail=100 api worker proxy
curl --fail http://127.0.0.1:8100/health
```

From an off-VM browser: navigate to **`https://<DEMO_HOST>`**, authenticate, create a fictional session, enter **mock** OTP, manually solve **mock** challenge, inject chaos, fill, approve and see a clearly synthetic receipt. Confirm screenshot updates and SSE events. **Never claim deploy success solely because `/health` returns 200.**

If DNS is unavailable on Day 1, use an **SSH tunnel** for a private team demo and disclose that public HTTPS deployment is not complete:

```bash
ssh -L 8100:127.0.0.1:8100 ubuntu@<VM_PUBLIC_IP>
# then visit http://127.0.0.1:8100 on YOUR local machine
```

## D. Day-1 browser-worker portal reachability check

This command **executes Playwright Chromium inside the VM's browser worker container**, not a local laptop or HTTP curl:

```bash
mkdir -p deployment-evidence
set +e
docker compose --env-file .env -f compose.yaml -f compose.vm.yaml exec -T worker \
  python scripts/portal_reachability.py \
  > deployment-evidence/portal-reachability.json
PROBE_EXIT=$?
set -e
cat deployment-evidence/portal-reachability.json
printf 'Portal probe exit code: %s\n' "$PROBE_EXIT"
```

A nonzero probe exit means one or more public landing pages failed; **investigate rather than hiding failures**. The curated read-only probe covers NSP, TN e-Sevai, TN welfare and MyScheme. It never logs in or attempts to bypass human security controls. Add one more verified portal candidate manually to reach the document's 4–5 research requirement (the four included are initial research targets, and MyScheme is a discovery portal, **not** an application portal). Record which pages need applicant or institutional accounts and Aadhaar face-auth.

Use the worksheet in `docs/PORTAL_RESEARCH.md` to decide which 2–3 sites are **legally and technically eligible for full flow testing**. If none permits testing, limit claims to mock flows and make this visible to judges.

## E. Acceptance table (fill with factual evidence)

| Requirement | Evidence | Initial status |
|---|---|---|
| Mumbai VM | Console/CLI region proof, instance identifier masked | **NOT DEPLOYED** |
| Compose + worker | `docker compose ps` + healthy worker/browser + DB volume | **NOT VERIFIED ON VM** |
| Public HTTPS/TLS + access control | Trusted external-browser login + cert details | **NOT VERIFIED** |
| Live screenshot and audit | Real UI recording from VM | **NOT VERIFIED** |
| 4–5 portal page reachability | JSON output from worker container | **NOT RUN** |
| Portal shortlist with blockers | Portal research sheet with verified actual constraints | **DESK RESEARCH ONLY** |
| 2–3 portal adapters | Authorized end-to-end demonstrations | **0 LIVE ADAPTERS** |
| Five E2E runs per chosen real portal | Timestamped run log, no credential leaks | **0 REAL RUNS** |
| Chaos script integration | Injection endpoint + shared script in worker | **BASIC NAMED DEMO CHAOS ONLY** |
| Demo video (2–3 min) | Actual MP4 recording from deployed app | **NOT RECORDED** |

## F. Operational requirements / safeguards

- Freeze `contracts/` with core and remote teammates before integrating. Core owns LangGraph/orchestration, skill library and encrypted vault; remote teammate owns chaos script, extraction, etc. Browser teammate owns worker/portal adapters/frontend/server/deploy/video.
- Run integration smoke using **deployed** API (`scripts/smoke.py` currently hardcodes localhost, so run from VM and record evidence; Codex should add configurable base URL + CI deployed path).
- Never accept arbitrary user-supplied portal URL or arbitrary JavaScript through public chaos endpoint; keep allowlists and script-name validation.
- No automated CAPTCHA solving, OTP interception/bypass, or Aadhaar device-auth emulation; require human actions. Never submit real applications without genuinely eligible applicants and verified consent.
- Do not use this demo code for real-person PII, public open registration or uncontrolled internet exposure. For real citizen applications, add identity/OIDC, granular permissions, audit, secure secrets/vault, encryption and retention compliance first.
- Keep backups and a rollback image tag before changes; use restricted cloud permissions, OS updates and separate production-grade secrets management for future real work.
- Define `feature freeze` and video schedule per work split: **Sunday 1 Nov 2026, 6 PM** submission assets final; internal submit goal **10 PM** (platform cutoff indicated **11:59 PM**).

## Codex instructions

**DEPLOYMENT IS P0.** On receiving this repository: (1) preflight + full HTTP Playwright E2E locally; (2) get Mumbai VM, domain/access and secrets from user if unavailable; (3) deploy worker/API/frontend with Compose; (4) prove public HTTPS login / browser screen and portal reachability **from worker on Day 1**; (5) fix any Docker/Playwright or reverse-proxy issues; (6) integrate core interfaces, add verified portal adapters as authorization permits, rerun 5x/portal; (7) record video. You may **replace this entire boilerplate** with a different architecture to meet requirements. You must not invent VM credentials, accounts, DNS, portal permissions or deployment outcomes.
