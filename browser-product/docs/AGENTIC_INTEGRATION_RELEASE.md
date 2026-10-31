# Agentic Browser Product — update verification and remaining obligations

Updated: **31 October 2026**. Scope: **only** `browser-product/` on the
`feat/browser-product` branch. Compared with uploaded `next-wave-main.zip`.

## The real integration change

Your teammate's LangGraph remains the sole autonomous decision maker. It has a
`Planner` that receives masked, source-grounded browser snapshots and chooses
an action. This update connects it to your actual Playwright worker rather
than the demo implementation.

- Worker adapter: `browser/core_compat.py` exposes `/core/session`, `/login`,
  `/snapshot`, `/action`, `/authorize-submit`, `/view`, `/close`. The UI is live
  DOM, **not** pre-scripted navigation. No invented CSS selectors.
- Secure gateway: `server/core_gateway.py` exposes the corresponding
  `/core-browser/session` API with a server-only shared key. Worker stays off
  the public Internet.
- Safety: exact origin and portal registry, observed element name/ref
  grounding, DOM/text freshness checks, human-provided OTP/challenge answers,
  field provenance, no OTP storage/replay, no unapproved final submit, guarded
  POST and failure-on-uncertain-receipt.
- Main integration: the older four-file patch was **removed** after it became
  incompatible with the teammate's updated main. Guidance is in
  `docs/BRIDGE_FIX_HANDOFF_OCT31.md`. Core LLM and LangGraph nodes remain untouched.
- Real-page mode: `APP_MODE=integrated`, signed identity requirement,
  operator-approved portal URLs, default-disabled form POST/final submit, and
  the synthetic website routes hidden.
- Existing v2 general browser actions remain available (`navigate`, `back`,
  `scroll`, `switch_tab`, `extract`, `select`, `check`, etc.). The old main
  Planner uses its four existing verbs but follows links autonomously.
- Human-only screenshot view at `/core-browser/session/{id}/view`, accessible
  with server key; **never** forward unverified screenshots to WhatsApp/LLM.

## Verified here

- `pytest -q -k 'not test_direct_control_stale_frames_and_stage_boundary'`:
  **30 passed, 1 skipped, 1 deselected**. New real-Chromium DOM test proves
  ordinary button click, verified field fill, stale-visible-review detection,
  review-observation-bound submit approval, single use, and receipt matching
  on synthetic content. Gateway key and forwarding tested.
- The outdated main patch is not shipped. No main branch integration is claimed by this release.
- Python files compile; Docker Compose YAML parses with PyYAML.

## Not verified / cannot claim

- Full networked browser worker against a running portal: Chromium in this
  environment fails URL navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`; the
  new HTTP local-portal smoke test is explicitly skipped here.
- The pre-existing `test_interactive_control.py` relies on Playwright's
  bundled headless shell absent from this environment; a full unfiltered run
  stops on that missing executable. In the Docker image Playwright 1.57 browser
  is expected, but Docker has not been executed here.
- Core main full tests were not executed: this environment lacks main's
  LangGraph/aiosqlite dependencies (the patched files compile and apply).
- Neither a real government application, login, CAPTCHA, Aadhaar face auth,
  receipt/status, Mumbai deployment, Telegram/WhatsApp end-to-end handoff,
  nor 5× multi-portal runs have been verified.
- Real portal anti-bot measures, submission policy, login flows and allowed
  origins require permission and live validation. Treat the current code as an
  actual browser tool layer, **not** a production-certified system.
- Browser contexts are held in a single worker process, not restorable across
  crashes. Core must re-open/re-authenticate and reconcile uncertain actions.

## Before real use

1. In VM, verify exact portal HTTPS and all required asset/auth origins;
   check the specific portal's written rules/permission.
2. Configure TLS reverse proxy, scoped user access, keys, encryption, backups,
   audit/event retention, and resource isolation.
3. Deploy browser worker + API in Mumbai and keep worker private.
4. Apply only the reviewed patch to a **separate core integration branch**, then
   set `BROWSER_WORKER_URL=https://browser-host/core-browser` and
   `BROWSER_WORKER_KEY` in the main service.
5. Execute full conversation **with his actual LLM and chat service**: request
   → decisions → real navigation/form → user Q&A → human auth → review →
   optional approval-gated submit → receipt/status.
6. Investigate target-specific receipt/parsing and optional controlled
   form POST enablement. Never bypass anti-bot or invent successful submissions.
7. Measure 5 runs on each of 2–3 real authorized portals, record failures and
   trace provenance. Test chaos injection separately.
