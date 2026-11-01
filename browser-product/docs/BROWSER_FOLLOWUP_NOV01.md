# Browser follow-up — 1 November 2026

Changes apply only to next-wave-browser-update/browser-product. No core graph,
.env, credentials, deployment or teammate main files were changed.

- clients/core_browser.py: open_url(url, consent_ref) has no demo fallback.
  Core must call it with the site chosen for the citizen request. The browser
  cannot override a Selenium URL deliberately sent by the existing graph.
- step(session_id, decide): one caller-requested step. Takes a snapshot and
  pauses on snapshot.challenge (including numeric OTP). The core supplies the
  decide callback. Reobserves and calls decide again only for known pre-action
  stale-page 409, bounded to two replans by default. Never blindly replays a
  write after timeout, network failure, human takeover or approval rejection.
- Assistance preview: detects CAPTCHA pixels identified by image ID/class,
  accessible context and challenge frame metadata, including data/blob URLs.
  Only a person clicks bounded regions. The UI sends its observation ID and
  stale control/coordinate actions require refresh. This is not a solver.
- Open cleanup: new context, new page, request routing and navigation share a
  cleanup boundary. Setup failures close their context rather than consume
  capacity. Safe failure categories and a diagnostic reference appear in
  both the error response and worker logs; no raw URL or exception is logged.

## Core owner wiring

Use CoreBrowserClient with the browser API host (without /core-browser suffix)
and server-only service key. Call open_url(selected_url, citizen_consent_ref),
then step(session_id, existing_planner_callback). It is an optional adapter;
adding this file does not automatically change the deployed graph. Keep the
existing LangGraph and WhatsApp/Telegram identity and message handling.
If step pauses for verification, create human_task(session_id, challenge_kind),
privately deliver assistance_url, poll completion, and re-snapshot before
continuing. A completed handoff is not proof of successful authentication.
Keep final submit disabled unless using the reviewed approval adapter.

## Validation limits

Tests cover fresh replanning instead of replay, no retry on uncertain outcome,
numeric OTP pause, exact URL forwarding, failed-new-page cleanup, CAPTCHA image
coordinates, stale preview rejection and the existing dedicated-upload policy.
A local HTTP test also checks that a real multipart upload reaches its target.
These checks do not certify the original Azure page or the live chat bot.
The one-off open failure's original cause remains unknown. For a recurrence,
record its HTTP status/reference and match the worker log, then run the existing
read-only navigation diagnostic inside that worker. No deployment was done.

Verified locally: full pytest suite **81 passed** with one upstream Starlette/httpx deprecation warning (161.78 seconds). Assistance JavaScript passed node --check. Tests used installed Chromium, synthetic data and a local upload HTTP server; no model tokens, live Azure changes or external messages.
