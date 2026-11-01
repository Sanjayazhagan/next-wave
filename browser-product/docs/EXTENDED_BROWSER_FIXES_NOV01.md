# Extended browser reliability pass — 1 November 2026

The browser tool service owns these changes. The latest teammate graph/chat
service is not modified. The synthetic fixtures exercise browser behavior;
public sites can still refuse access. No CAPTCHA bypass or automatic citizen
consent is implemented.

| Item | Resolution / verification |
| --- | --- |
| 1. Ordinary search mistaken for final submission | Search-only GET form detection plus exact reviewed search destinations. Built-in reviewed targets are Google /search and Wikipedia search paths. Other destinations need BROWSER_SEARCH_TARGETS_JSON. POST, mixed forms and final action wording retain existing gates. |
| 2. Dynamic target staleness | Fresh bounded replanning in client helpers for known non-applied stale actions. Duplicate-label reordering is refused rather than retargeted. No uncertain-write replay. |
| 3. Overlays | Observations expose visible dialogs with scoped control metadata; planner instructions explain overlay-first interaction. No forced clicks, automatic consent or generic dismissal. |
| 4. Busy worker | Preserve Retry-After at gateway; helpers retry safe reads or explicitly non-applied 429/503 responses at most twice, respecting short delay hints. Longer delays return to caller scheduler. |
| 5. Action effects | Report changed URL, new tabs, started downloads, changed content and validation evidence separately. None implies a verified application receipt. Core bridge returns effect evidence too. |
| 6. Duplicate labels | Browser regression reorders same-label controls and verifies refusal with no wrong click. |
| 7. Autocomplete/custom dropdown | Observe ARIA options, comboboxes and selection state. Selecting an option requires verified source; text entry alone is not selected-value proof. |
| 8. Date/multi-select | Native date and multi-select readback tested; custom calendar gridcells exposed and source-gated. Nonstandard inaccessible widgets still need site-specific human/adapter handling. |
| 9. Popup/download | Separate event evidence; popup tab remains explicitly selectable. Download-start evidence is not download integrity or a portal receipt. |
| 10. Delayed validation | Observe/wait before deciding success; delayed error fixture proves ordinary click does not claim final acceptance. No universal wait-for-all-network-idle rule. |
| 11. Session expiry | Closed context returns explicit ended/lost error; no hidden reopen or credential replay. Caller must reauthenticate. |
| 12. Lost submission response | General helper retains original action and refuses a fresh ID; durable gateway unknown-outcome quarantine and core uncertainty protections remain. |
| 13. Multi-step resets/uploads | Post-action snapshots reveal replaced/cleared fields; attachment readback and scoped upload confirmation remain separate from final acceptance. |

DOM objects have document-local identities so identical-label controls cannot
silently swap under the same index. File objects are immutable: a new selected
File identity (even with the same filename/size) changes a keyed digest and
invalidates a prior final review. Raw file metadata is removed before returning
observations. These identities are freshness signals, not protection against
a deliberately malicious website forging its own page content.

## Search configuration

`BROWSER_SEARCH_TARGETS_JSON` is an optional JSON list of exact HTTPS URLs,
without query or fragment, for operator-reviewed GET search forms. Example:

```dotenv
BROWSER_SEARCH_TARGETS_JSON=["https://approved.example/search"]
```

Search forms must contain only query text inputs/textarea, language selectors,
hidden fields, fieldsets and submitters.
The request scope is single-use and the origin must match the page. Localhost
HTTP targets are accepted only as explicit operator entries for synthetic
testing; public-web destination policy still prohibits private HTTP access.
This does not enable application, payment, account or arbitrary form POSTs.

Live retest: Wikipedia Search reached `/wiki/Space_exploration`. Google Search
passed the browser policy and returned Google's anti-bot page; Google results
are not claimed. MDN search overlay opened and accepted field input.
Download events can arrive after the immediate action response; the cumulative
`downloads_started_total` observation supports later inspection without
claiming that download bytes were saved or verified.

## Integration

Use the current Python helpers as reference implementations. Existing teammate
clients do not gain retry logic just by deploying the worker. Teach the planner
to inspect `interaction_state`, observed ARIA roles, selected/expanded state,
effect evidence and the current snapshot after each action. Never treat
`ok: true` or a file attachment as confirmed application completion.

DOM/labels are untrusted page data. Real identity, OTP, CAPTCHA, approval,
receipt adapters and deployment checks remain required for live workflows.
