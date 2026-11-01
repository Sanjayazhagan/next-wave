# Four-site resolution — 1 November 2026

## Fixes

- DOM references now use document-local object identity rather than numeric
  positions. Ad/widget insertions no longer invalidate an unchanged target.
  References are opaque; callers must not parse them or reuse across contexts.
- Actions bind the verified DOM object, avoiding a mutable nth-element locator
  selecting a different control after a DOM insertion. Replaced objects still
  require a fresh observation. Strict final-review freshness remains.
- A keyed digest preserves link/form query freshness while raw query values
  remain omitted from observations.
- Link actions wait briefly for delayed client-side navigation before capturing
  their result. A timeout still does not imply navigation or application success.
- Offscreen clicks scroll and settle within bounded time before actionability
  testing. No forced click is used.
- DOM census stops scanning once its visible-result budget is known exceeded.
- Visible consent iframes are identified as `consent_required`, with a
  `citizen_choice_required` human signal. Reference clients pause explicitly.
  Tiny/offscreen consent-labelled tracking frames do not trigger this state.

## Actual public verification

| Site | Result |
| --- | --- |
| Flipkart | Help Center reached at `https://www.flipkart.com/helpcentre`. An optional login promotion appeared after scrolling. The bounded caller selected its observed ordinary close button, then clicked Help Center. No authentication or forced click. |
| Node.js | Learning materials reached `https://nodejs.org/learn`; action effect now reports URL change, with destination title observed. |
| CNN | World link reached `https://edition.cnn.com/world`; destination title and URL-change effect observed. |
| Guardian | Inspection returned ready; the actual blocker was an iframe titled “The Guardian consent message.” Now explicitly classified as user consent, not a generic incomplete inspection or blind retry. No consent choice was made. Science navigation remains dependent on the person's choice and is not claimed as verified. |

The main graph must inspect obstruction/consent metadata and choose appropriate
observed controls. The worker does not autonomously dismiss prompts. Closing
an optional login advertisement is distinct from bypassing required login.
There is no automatic consent acceptance or rejection. A dedicated interactive
consent-provider handoff was not verified; the reference helpers currently
pause for the citizen's choice.

## Validation

Full suite: 133 passed, one upstream Starlette/httpx deprecation warning.
After narrowing iframe visibility detection, the stable-target/navigation test
module was rerun (including large and tiny consent-frame cases); results are
recorded in FOUR_SITE_VALIDATION.json. No Docker/cloud or actual main-agent/chat
integration claim. Website evidence is in the external workspace's
output/four-cases-probe/results.json and output/flipkart-recovery-final/result.json.
