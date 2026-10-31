# Browser Product ↔ main LangGraph: source-grounded integration

**Read this before trying to merge branches or claiming real-portal support.**

## Actual source comparison

`next-wave-main.zip` has a LangGraph in `app/graph/{builder,nodes}.py` and an
LLM-driven portal planner in `app/planner.py`. The `app/browser.py` HTTP client
expects a compact worker contract:

| Core call | Browser Product gateway call | Behavior |
|---|---|---|
| `open(portal_id)` | POST `/core-browser/session` | Resolve an operator-reviewed portal ID, launch isolated Chromium context, open page |
| `login(session_id, portal_user_id)` | POST `/core-browser/session/{id}/login` | Fill a unique, observed user-ID field if present; never bypass OTP/Aadhaar |
| `snapshot(session_id)` | GET `/core-browser/session/{id}/snapshot` | Convert live DOM to `PageNode` roles/names and mask sensitive values |
| `act(session_id, action)` | POST `/core-browser/session/{id}/action` | Click, fill, upload, wait; verify observed target and field source |
| `authorize_submit(...)` | POST `/core-browser/session/{id}/authorize-submit` | Single use, 120-second approval bound to current review observation |
| `close(session_id)` | DELETE `/core-browser/session/{id}` | Dispose browser state and session |

The gateway lives in the Browser Product **API** (`server/core_gateway.py`). It
requires `X-Internal-Key`; it proxies to the **private worker** (`browser/core_compat.py`).
**Do not expose the worker port on the Internet.**

Core continues to plan actions using its existing `Planner`, `SkillStore`,
LangGraph graph, encrypted vault, and communication channel. The bridge **does
not** invent an alternative AI agent. The v2 browser API remains available for
future richer actions: `navigate`, `back`, `scroll`, `select`, `check`, `extract`,
`switch_tab`; the existing core planner initially clicks the observed links.

## Configuration / new security invariants

In Browser Product set:

```ini
APP_MODE=integrated
SECURITY_MODE=signed
INTERNAL_KEY=<strong randomly generated secret>
APP_SIGNING_KEY=<different secret>
IDENTITY_SIGNING_KEY=<separate 32+-character secret>
DATA_ENCRYPTION_KEYS=<Fernet key(s)>
BROWSER_ALLOWED_ORIGINS=https://authorized-example.gov.in
BROWSER_PORTALS_JSON={"authorized_scheme":{"url":"https://authorized-example.gov.in/login"}}
BROWSER_ALLOW_FORM_POST=false
BROWSER_ENABLE_FINAL_SUBMIT=false
```

In Core `main` set:

```ini
USE_STANDINS=false
DEFAULT_PORTAL_ID=authorized_scheme
BROWSER_WORKER_URL=https://browser.example/core-browser
BROWSER_WORKER_KEY=<same INTERNAL_KEY>
ALLOW_REAL_SUBMIT=false
```

The existing core has **no built-in way** to send this service key or to
authorize the final reviewed click, so apply the four-file patch in
`integrations/next_wave_main_patch` only after review. It intentionally leaves
all agent/planner/channel logic and core deployment intact.

## Important real-world limits

- Generic page automation **cannot promise** success on every government site.
  SSO, captcha, Aadhaar face auth, JavaScript heavy flows and anti-bot controls
  require portal authorization and appropriate user takeover. Never bypass.
- Browser origin policy is exact-operator-allowlist, and generic actions cannot
  independently submit. Real site intermediate form POSTs are disabled by
  default; opt in `BROWSER_ALLOW_FORM_POST=true` only after reviewing the site.
  This toggle does NOT approve the final submit action.
- Core's current planner uses `click/type/upload/wait`. For more expressive
  browser navigation/research, integrate the existing `/integration/v2/browser`
  protocol in a later scoped improvement, retaining core as decision maker.
- Core's `portal_login` cannot do automated password/face-auth; the adapter
  only fills a visible user ID. Authentication requires an explicit human step.
- Generic receipt capture requires a real portal-specific `receipt_pattern`
  **and** explicit success text. It will otherwise hand off rather than invent.
- Screenshots from arbitrary real pages are **not** marked safely masked; do not
  send them to WhatsApp or LLMs by default.
- Browser sessions remain live in a single worker process. A crash loses the
  Playwright context; core should reopen and re-authenticate, then replay only
  safe, verified steps. This is not seamless state recovery.

## End-to-end validation before demonstration

1. Run both applications separately, check their `/ready` or `/health`.
2. Prove core `/session` triggers a call to Browser Product `/core-browser/session`
   using its service key and creates a worker Chromium context.
3. Send an observed page into **core's actual LLM**; verify it chooses a link,
   click, field, next step and core enters only sourced values.
4. Trigger a changed field label; verify core's existing skill repair path.
5. Trigger login/OTP/CAPTCHA; verify core pauses and asks the citizen, not the model.
6. Trigger final review; verify unsigned/unapproved click is 403, approved
   review bound to current observation passes once and never auto-retries.
7. Verify real receipt/status **only** with explicit portal-specific evidence.
8. Test VM origin reachability, TLS, Docker restarts, keys, audit and review.
9. At least five full runs per each of two or three operator-approved flows;
   count blocked/handovers honestly.

**Deployment:** main teammate's existing Railway API can remain separate.
Browser Product + Playwright should be on a Mumbai VM behind HTTPS/reverse
proxy, with worker private and an explicitly verified outbound destination
allowlist. No Mumbai VM deployment is claimed by this package.
