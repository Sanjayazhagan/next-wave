# Audit of demo shortcuts and integration boundaries

31 October 2026 IST. Earlier descriptions overstated general browser readiness. Working scholarship fixtures and security/operations controls did not mean that a model could interpret and navigate an arbitrary site. This audit identifies the concrete shortcuts and replacement paths.

| Prior shortcut | Current reusable replacement | Actual boundary |
|---|---|---|
| Fixed five scholarship fields | v2 DOM controls with labels, types, required/disabled/read-only state, validation constraints/options and evidence references | Core model maps citizen data; worker does not guess values |
| Saved labels and a known renamed-income fallback | Observation-scoped target refs and stale DOM/generation checks | Core owns semantic repair/skill learning; stale actions fail rather than guessing |
| Only fill/click on known form | Typed click/fill/select/check/upload/navigation/back/scroll/wait/tab/extract actions | Final submit and auth are excluded from general tools |
| Only /mock navigation | Separate contexts with trusted configurable exact-origin policy | Default origin remains local; configuration is not proof of real-site authorization |
| Single-page assumptions | Frame inventory, permitted frame controls, shadow-DOM controls, popup/tab inventory and switching | Unsupported/cross-origin frames are reported unavailable; closed tabs fail explicitly |
| Screenshot and ARIA only | Structured fields/constraints, headings, alerts, tables, page text, ARIA and masked screenshot | Content is untrusted website data; baseline redaction is not real-portal privacy certification |
| Fixture extraction via window.demoReviewData | General control-value extraction and document structure independent of mock globals | Legal/official data interpretation remains with core/rules |
| Fixed synthetic PDF upload | Owner-bound encrypted PDF/PNG/JPEG artifacts, signature checks and observed accept constraints | Default 1 MB service budget; actual portal dimensions/limits still need verified manifests |
| No model-facing contract | ModelPort, provider-neutral input with trust instructions, strict ModelDecision schema and grounded-output validation | No model/agent is bundled or claimed to have run |
| Demo coordinator implied a real agent | v1 remains labeled fixture; separate /integration/v2/browser and GeneralBrowserClient expose tool primitives | Actual LangGraph and model reasoning remain core-owned |
| Console only monitored scholarship flow | Read-only general workbench and view API that preserve the model's observation refs | Signed ownership/operator checks apply; default local demo is synthetic only |
| Mock CAPTCHA arithmetic presented as human integration | Existing working demo handoff plus general auth-risk observations and HumanRegionAdapter boundary | General official challenge regions/completion need a reviewed adapter; do not claim universal CAPTCHA support |
| Fixed review/receipt/status fixture | General tools block submit; explicit ReviewAdapter/ReceiptAdapter contracts identify required trusted operations | Those real adapter implementations do not exist without authorized observations; fixture receipts remain fixture-only |
| Profile provenance fixture | Source-aware verified field actions and encrypted subject-scoped artifact references | 'Verified' is an assertion from trusted core, not a replacement extractor/doctor |
| Core skill/decision assumptions | Explicit CoreSkillPort, VerifiedProfilePort, ModelPort and capability discovery | Protocols are interfaces, not successful placeholder services |
| Browser loss might look resumable | Generation-scoped observations, persistent context/action metadata, unknown-outcome barriers and explicit lost context state | Cookies/authentication are never fabricated or automatically resurrected |
| Source ZIP checked for hashes but not fresh runtime | Fixed omitted web/ allowlist; fresh extraction, new venv, pinned dependency install and packaged HTTP E2E | No Docker/Mumbai or fresh external-service integration is implied |

## General-browser implementation and verification

browser/general.py and general_routes.py are independent of the scholarship adapter. server/browser_v2.py is the authenticated core gateway. browser/protocol.py supplies model input/output and action schemas. clients/general_browser.py supplies observe/model-input/apply-decision calls without creating an agent. browser/extension_ports.py declares portal-specific operations that general page interpretation cannot safely prove.

scripts/verify_general_browser.py runs actual API/worker HTTP and Chromium against a separate multipage workshop fixture. It verifies navigation, field discovery, typed values, select/checkbox, iframe and open shadow-root fields, owner-scoped upload, popup/tab switching, value/table extraction, sensitive-value masking, stale-ref rejection, submit rejection, model target validation and the general SDK. Its decisions are scripted. It is not evidence of model reasoning or a government adapter.

## Still intentionally unavailable

No actual model/provider is connected. No LangGraph/WhatsApp/rules/extraction/doctor/core vault is implemented here. No generic action may submit a form or make POST writes. GET-only requests can still have server-side effects; configure this framework only for authorized/test destinations and verify each real workflow. Authentication, human challenge completion, exact final review/submission and authoritative receipt/status reconciliation must be provided by reviewed portal adapters and core authorization. Missing adapters remain unavailable rather than silently calling the scholarship fixture.

External services, real authenticated sites and deployment remain release gates. See GENERAL_BROWSER_V2.md for the implemented wiring surface and OPERATIONS_AND_SECURITY.md for storage/access boundaries.
