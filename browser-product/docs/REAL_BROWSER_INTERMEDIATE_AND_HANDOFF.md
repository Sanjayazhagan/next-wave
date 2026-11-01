# Real browser: intermediate actions and human assistance (31 October 2026)

## Scope

**This is a browser-branch-only implementation.** It does not modify `main`, embed an LLM, change teammates' LangGraph planner, or send WhatsApp messages. The bridge exposes an authenticated REST interface for the existing agent; humans operate their *own live browser session* through an expiring URL when needed.

**What changed**

- `browser/step_policy.py` classifies observed controls as `otp_send`, `otp_verify`, `human_input`, `file_input`, `upload_step`, `intermediate`, `final` or `final_unknown`. The field appears as `action_category` in `/core-browser/session/{sid}/snapshot` nodes. This is a heuristic, **not** authority for an irreversible action.
- OTP requests can be triggered by the existing core `click` operation when a clearly observed OTP-request button is on an authentication page, limited to **2 per 10 minutes per session**. They are never logged with a code value.
- OTP verification is performed by the citizen, or after an explicit citizen response through the existing core interface. The link limits human verification attempts to **5 per browser session**.
- A document Upload button is distinguished from final Submit Application. Autonomous upload-form POSTs require the site's exact origin in `BROWSER_INTERMEDIATE_POST_ORIGINS`. A citizen may instead click an observed Upload Document control in the scoped human assistance view once a file is attached. Both remain blocked if the destination resembles final submission.
- `Next`, `Continue`, and `Save Draft` controls are represented as non-final. Where they cause POSTs, **the exact origin must be operator reviewed**; POST is still blocked by default. The code does **not** silently infer whether an unseen server-side POST is final.
- Form controls are discovered **before** long lists of navigation links, so the 250-control observation budget is less likely to hide fields.
- Human-only CAPTCHA provider POSTs are permitted only during a live assistance task, only to a narrow set of recognized provider HTTPS challenge URLs. CAPTCHAs are **never solved by software**.
- Final Submit, Payment, Delete, Withdraw and unknown submit controls still require separate approval. Generic public-web mode is **not** a fully audited final-submission adapter. Final submission defaults to off (`BROWSER_ENABLE_FINAL_SUBMIT=false`).

## Create a temporary human-assistance link

The existing LangGraph client authenticates every call with `X-Internal-Key: <INTERNAL_KEY>`.

```http
POST /core-browser/session/{sid}/human-task
X-Internal-Key: ...
Content-Type: application/json

{"reason":"otp","ttl_seconds":300}
```

`reason`: `otp`, `captcha`, `login`, `upload`, `verification` or `other`. The response contains `task_id`, `assistance_path`, `assistance_url` (when `DEMO_HOST` is configured), `expires_at`, and notes. An example URL format:

`https://<host>/core-assist/<task_id>#<secret-fragment>`

The fragment is never transmitted as an HTTP request URI. The user interface holds it only in JS memory and sends it in the `X-Assist-Token` header. The server stores **only its SHA-256 digest** in SQLite. The link lasts 60–600 seconds. Share it privately with the citizen; **WhatsApp sending is the core team's responsibility**.

The agent's normal `/session/{sid}/action` returns **409** while assistance is active. The citizen's link supports:

- A screenshot of the same Playwright session, refreshed on request.
- OTP/CAPTCHA text entry into observed authentication fields.
- Manual clicks on observed `Send OTP`, `Verify OTP` and `Upload Document` controls.
- Manual coordinate clicks **only** inside positively identified CAPTCHA image or iframe bounds.
- A button to return control to the agent. The response is `verified:false`: *the citizen says the step was done; the agent must re-snapshot the portal before treating authentication as completed.*

Checking status:

```http
GET /core-browser/session/{sid}/human-task
X-Internal-Key: ...
```

Cancel and revoke the link:

```http
POST /core-browser/session/{sid}/human-task/cancel
X-Internal-Key: ...
```

On expiry, the browser session automatically unpauses upon the next core action and the link is invalid. The core must inspect the page before proceeding and request a new link if verification is still required. Service restarts revoke in-memory control state; the core must reconcile and reissue a link.

**Constraints:** Browser screenshots are intended only for the human and can expose visible citizen data. Assistance must be sent to the *session owner*; do not post the URL in a group. No CAPTCHA or face-authentication bypass. Some CAPTCHAs use unsupported dynamic canvases, nested iframes or device apps; those still require the official app or an alternate approved manual flow. CAPTCHA provider POSTs are narrowly enabled, but not every real provider has been live-tested.

## Multi-step POST policy

`BROWSER_INTERMEDIATE_POST_ORIGINS=https://reviewed-portal.example` is still **required** for agent-driven intermediate form POSTs. This is not a per-page editing requirement; it is a one-time **operator safety approval** of the exact site. `BROWSER_ALLOW_FORM_POST=true` must never be used as a wildcard in public-web mode.

Do not infer safety from button text alone: a misleading “Next” could commit an application. For high-risk real portals, add a reviewed adapter that validates the target action, server request path and resulting state. The generic browser may only fill/read until such a review is complete.

## Owner split

**Browser teammate:** deploy the updated browser branch; manage API key, portal egress policy and consent-bound session handoff; make sure the public assistance link works over HTTPS; run negative security tests.

**LangGraph teammate:** call the new `human-task` API when observation indicates CAPTCHA/OTP or a reviewed upload-step needs a person; privately deliver the returned link through his authenticated conversation channel; poll task status; re-snapshot and replan after completion. He does not need to replace `nodes.py` or use the old main patch.

## Validation matrix

| Test | Local evidence | Still required on live Azure |
|---|---|---|
| Identify OTP-send vs final Submit | Unit & system-Chromium DOM | Actual OTP portal |
| OTP limit and human-only value entry | System-Chromium DOM | Correct/wrong OTP via authorized test account |
| Upload button distinguished from final | Unit & system-Chromium DOM | Authorized page-level file-upload POST |
| Save/Next POST scoped to reviewed origin | Route-policy tests | Multi-step authorized test portal |
| CAPTCHA image / iframe manual interaction | Bounds and route-policy tests | Real CAPTCHA website, no bypass |
| Expiring one-session link and revoke | Unit test | HTTPS link from a second device |
| Final Submit stays blocked | System-Chromium DOM | Real portal negative test |
| LangGraph-driven end-to-end flow | Not tested | Core team must integrate & test |

**Production-hardening blockers:** no VPN/egress firewall enforcement against DNS rebinding; no live real-portal validation; no multi-instance coordination for the in-memory browser session; no approval-verified real-portal final-submit adapter. Do not market as production-ready.
