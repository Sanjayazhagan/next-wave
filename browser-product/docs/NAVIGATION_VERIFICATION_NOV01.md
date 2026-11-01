# Browser navigation update — 1 November 2026

This release updates the browser execution service. The teammate's LangGraph,
LLM and chat services remain separate and have not been changed or deployed.

## Changes

- Batched, bounded DOM inspection; visible links consume the link budget rather
  than hidden links. Snapshots support `link_offset` and `link_query`.
- Accessible labels include multiple `aria-labelledby` references, image alt
  and SVG titles. Observations include form constraints, options, checked state,
  tabs, HTTP status, coverage and explicit page readiness.
- Ordinary actions validate the target's semantics rather than unrelated page
  clocks. Final approval retains strict review freshness, including a digest
  of bounded hidden form state. Hidden values are not returned to callers.
- Core actions support check/select/back/scroll/switch_tab. Verified field
  provenance is mandatory; checkbox consent must never be inferred.
- Dedicated upload confirmation is scoped to the attached file's reviewed form.
  Attaching a file and confirming upload are separate actions.
- Timeouts and lock contention are bounded. Known pre-action rejection is
  distinct from an unknown outcome. Unknown writes require reconciliation;
  retrying with a fresh action ID is unsafe. Preserve the original ID.
- Login/password submission is human-only through scoped assistance. Secrets
  are masked across navigation and cleared with browser context destruction.

## Core integration requirements

Adopt the updated `contracts/core-browser` schemas and optional snapshot fields.
Pause on non-ready `page_status`, human challenges or `needs_reconciliation`.
Use observed targets and current observations. Preserve action IDs across
transport errors. `X-Browser-Outcome: not_applied` permits correcting/replanning
a rejected action; `unknown` requires inspection and reconciliation.
Use `clients/core_browser.py` as the reference helper, not a replacement agent.
The browser does not implement the WhatsApp provider or main graph.

Generic final submission stays disabled. An operator can opt in a reviewed
native form with `BROWSER_ENABLE_FINAL_SUBMIT=true` and, for example:

```dotenv
BROWSER_FINAL_SUBMIT_TARGETS_JSON=[{"url":"https://authorized.example/submit","method":"POST"}]
```

The exact same-origin path/method must match and a fresh citizen approval must
still authorize the current review. This is a one-request scope, not wildcard
POST permission. Portal-specific success/receipt validation is still needed;
a click or navigation alone is not a verified application receipt.

## Verification evidence

Before the final accessible-label correction: 105 pytest tests passed; real
HTTP `verify_general_browser.py`, `verify_conversation.py` and
`verify_handoff.py` passed. These three scripts use synthetic portals/consumers;
no actual model or WhatsApp provider was called. Final suite results are
recorded in the release validation report.

Public trials on this Windows host, using synthetic values only:

| Flow | Observed result |
| --- | --- |
| NASA Explore → Missions → Artemis | Actual Artemis URL reached |
| Python Downloads | Downloads URL reached |
| Apple product link | Product URL reached, about 11 seconds |
| web.dev Learn more | AI topic URL reached, about 8 seconds |
| Test Pages form | Fill/select/check/upload readback passed |
| Heroku upload | Attachment and page upload confirmation accepted |
| Selenium native GET form | Fresh approved submission reached Received! |
| httpbin native POST form | Fresh approved submission echoed synthetic data |
| Google/GitHub identifier | Input readback passed; sensitive login click refused |
| Microsoft invalid identifier | Input and Next passed; site returned account lookup error |
| Amazon India | HTTP 202, empty page; no login verified |
| LinkedIn / W3C | HTTP 403 challenge/block explicitly reported; no bypass |
| Flipkart | Page observed; selected link obstructed, action refused before click |
| MDN | Snapshot/click returned; destination unchanged, navigation not proved |

Public trial results are in the external workspace output directory and are
not packaged as source. They are host-specific observations, not universal
website compatibility guarantees. The final accessibility fix has a local
real-browser regression test; the public sweep preceded that small correction.

## Remaining real-environment obligations

Integrate and test with the latest actual main graph and chat provider. Configure
portal authorization, real success/receipt adapters, signed identities, secrets,
TLS, private worker access, retention/monitoring and network egress isolation.
Verify container startup, restart recovery, concurrency/load and the complete
human authentication flow on the deployment host. Docker/Mumbai deployment,
real citizen applications and five runs on each authorized portal are not
claimed here. Browser contexts cannot survive a worker process crash; reopen,
re-authenticate and reconcile rather than replaying uncertain writes.
