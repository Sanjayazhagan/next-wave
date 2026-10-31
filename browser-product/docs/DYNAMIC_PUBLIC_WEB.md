# Dynamic public-website browsing (opt-in)

**Owner:** Browser & Product · FORGE '26 GradientZero · updated 31 October 2026

## Why this exists

The original `BROWSER_ALLOWED_ORIGINS` and `BROWSER_PORTALS_JSON` configuration restricted sessions to manually pre-registered sites. That is suitable for known application portals, but it is too rigid for an agent that discovers public information and follows links across multiple sites. The browser service now supports **dynamic public HTTPS URLs**, with **no per-site `.env` edits or Docker restart**.

This is a **browser execution service**, not a bundled LLM. The teammate's LangGraph planner chooses URLs/actions. No code in `main` is modified by this package.

## Enabling on your Windows laptop

Use the existing `.env` with independent strong `INTERNAL_KEY`, `APP_SIGNING_KEY`, `IDENTITY_SIGNING_KEY` and Fernet `DATA_ENCRYPTION_KEYS`. Add/change:

```dotenv
APP_MODE=integrated
SECURITY_MODE=signed
BROWSER_NAVIGATION_MODE=public-web
BROWSER_ALLOW_FORM_POST=false
BROWSER_ENABLE_FINAL_SUBMIT=false
```

`BROWSER_ALLOWED_ORIGINS` and `BROWSER_PORTALS_JSON` are **not required** in public-web mode. They may remain set for legacy registered portal IDs. The dynamic mode is deliberately opt-in; `allowlist` remains the default.

```powershell
docker compose -f compose.yaml -f compose.integrated.yaml config --quiet
docker compose -f compose.yaml -f compose.integrated.yaml up -d --build
docker compose -f compose.yaml -f compose.integrated.yaml ps
Invoke-RestMethod http://localhost:8100/ready
```

Do not publish your local port 8100 to the public internet. If collaborating remotely, use private, access-controlled Tailscale Serve and keep service keys solely on backends.

## Two supported API styles

Both require `X-Internal-Key` on the API gateway. Only a trusted agent backend, never browser-side JavaScript, should hold the key.

### A. Legacy-compatible LangGraph bridge (simple URL opener)

`POST /core-browser/session`

```json
{"url":"https://www.wikipedia.org/wiki/Playwright","consent_ref":"user-consent-2026-10-31-001"}
```

Response: `{ "session_id": "..." }`. Then `GET /core-browser/session/{id}/snapshot`, `POST /core-browser/session/{id}/action`, and `DELETE /core-browser/session/{id}`. For a new dynamic URL, provide a nonempty consent reference issued by the trusted core. **The current bridge checks presence/shape of this reference; it cannot independently prove the citizen actually consented.** The main agent must verify and store consent.

The older `{ "portal_id": "test" }` request remains supported if that ID exists in `BROWSER_PORTALS_JSON`. The teammate's current LangGraph `open(portal_id)` sends only that older shape. He will eventually need a **small optional client/contract change** to pass `url` and `consent_ref` for dynamic browsing, or use the v2 API. No need to change his whole planner.

### B. General browser v2 (richer tools)

`POST /integration/v2/browser/contexts`

```json
{"request_id":"unique-request-000001","subject":"consented-user-id","consent_ref":"user-consent-2026-10-31-001","url":"https://www.wikipedia.org/wiki/Playwright"}
```

Then `GET /integration/v2/browser/contexts/{id}/observe`, model input and actions. Navigate freely among public HTTPS sites using a `navigate` action with the **current observation ID**. Each action uses a unique action ID. See `docs/GENERAL_BROWSER_V2.md` and `browser/protocol.py`.

## Security boundaries

The policy enforces: HTTPS port 443 only, rejects URL credentials, IP literals that are private/reserved/loopback/link-local, single-label/internal names, and DNS answers containing any non-global IPv4/IPv6 address. The browser's request interceptor applies the checks to main pages, redirects and subresources. POST and final submission remain disabled by default. Existing human OTP/CAPTCHA and citizen approval requirements remain in place.

**IMPORTANT LIMITATIONS:** These checks are defense-in-depth, **not a complete SSRF isolation boundary**. DNS rebinding between DNS validation and Chromium's connection can still occur. Run the browser in a VM/network with egress rules that prohibit access to private networks, host services and cloud metadata before exposing it to untrusted remote users. The existing Docker/Chromium configuration is for controlled hackathon testing, not a production sandbox for arbitrary untrusted pages. JavaScript-driven side effects and destructive GET endpoints are not perfectly detectable. Use operator authorization and user consent for real targets. Do not automate CAPTCHA/OTP bypass or claim unrestricted safe access to any site. Some sites forbid automation or block bots.

## What was tested

- Unit tests for public/private URL filtering, DNS answers, and route interception.
- Legacy core bridge accepts URL+consent in dynamic mode while rejecting it in allowlist mode.
- Browser DOM tests reuse the existing Playwright fixture.
- Full live internet navigation and deployed LangGraph integration **must still be tested on the user's Docker Desktop**; no such success is claimed by this handoff.
