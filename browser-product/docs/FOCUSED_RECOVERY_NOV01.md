# Search and interaction recovery follow-up — 1 November 2026

Applied scope: browser execution service and reference clients, not the
teammate's actual graph. One bounded 15-site pass covered the hosts with
previous search/stale/obstruction refusals. Two diagnostic search clicks and
one NOAA correction check were performed; there was no repeated website sweep.

## Changes

- Reviewed exact GET search destinations for Walmart `/search`, IKEA
  `/us/en/search/`, DuckDuckGo `/` and Coursera `/`. Existing query-only form
  checks and network destination validation still apply. Other regions,
  endpoints and arbitrary forms are not automatically approved.
- Source-bound NOAA handoff: `https://www.noaa.gov` to
  `https://search.usa.gov/search`. Both origins are normalized with default
  ports. Unrelated source origins and POST requests remain refused. In fixed
  allowlist mode the target origin must also be explicitly allowed.
- `blur` action for an observed ordinary editable control. This releases
  autocomplete focus; it does not press Enter, submit, infer consent or
  interact with password/OTP/CAPTCHA fields.
- Observations expose `occluded`, `blocker` and `requires_scroll` hints, plus
  visible listboxes/menus and sensitive-overlay flags. Playwright actionability
  trials remain authoritative; hints never enable forced clicks.
- Current Python client `step` supports at most two fresh replans after known
  non-applied stale/obstructed actions. Unknown outcomes remain unretryable
  under a new ID. The focused runner uses this helper and observed targets.
- Updated v2 schemas include `blur`; snapshots carry the additive hints.

## Public evidence and honest limits

| Case | Observed result |
| --- | --- |
| Walmart | Search GET reached `/search`, page ready |
| IKEA | Search GET reached `/us/en/search/`, page ready |
| Coursera | Search action reached `/search`, page ready |
| DuckDuckGo | Direct search check navigated with changed URL/content, page ready; the first runner skipped its occluded-button hint |
| NOAA | Regression test caught default-port mismatch; corrected handoff navigated to government search host, which returned empty/loading content. Search results are not verified. |
| Bing | News search URL reached |
| Wikipedia | Space exploration article reached |
| MDN | Blog URL reached |
| BBC | News URL reached |
| LinkedIn | Ordinary identifier readback and homepage navigation; no login |
| web.dev | Discover URL reached |
| Flipkart | Input/blur worked; a later action still exhausted bounded recovery with HTTP 409. No force click or success claim. |
| Guardian | Final observation incomplete; flow is not verified |
| Node.js / CNN | Action returned but URL-change effect was false; no completed navigation claim |

Overlay recovery remains guided by observed controls. Consent/security dialogs
require the person; arbitrary inaccessible widgets or persistent obstructions
may require a portal-specific adapter. Deployment alone does not update the
teammate's planner to choose `blur` or read these new hints.

Validation details are recorded in FOCUSED_RECOVERY_VALIDATION.json. External
workspace evidence is under output/focused-recovery-final-nov01 and
output/search-handoff-diagnostic-nov01. No actual model/chat, Docker or cloud
deployment is claimed.
