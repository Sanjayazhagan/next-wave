# Model-facing browser framework v2

This is a browser-tool framework, not an AI agent. Core supplies its chosen model/LangGraph and decides what to do. The worker observes and executes validated tools. The scholarship demo remains a separate v1 adapter; v2 never uses its field names or window.demo functions.

## Trusted configuration

Configure encrypted storage keys and INTERNAL_KEY. Set BROWSER_ALLOWED_ORIGINS to a comma-separated list of exact HTTP(S) origins reviewed by the operator. Default is MOCK_BASE_URL only. Public API callers and model output cannot expand it. Requests outside those origins or using methods beyond GET/HEAD/OPTIONS are blocked. This conservative generic mode does not authorize final submit, login POSTs or other writes. A GET can still cause side effects on a poorly designed site; use authorized destinations and dedicated policies.

## Core loop

All routes below require X-Internal-Key and live under /integration/v2/browser.

1. POST /contexts with request_id, url, subject and consent_ref. The origin must already be configured. Persist returned id and generation; this execution context is separate from v1 scholarship sessions.
2. GET /contexts/{id}/observe for current observation_id and element refs. Includes labels/types, required/disabled/read-only/validation constraints, options, values, links, frame/tab inventory, text, ARIA, headings/alerts/tables and a screenshot. Authentication/identifier fields are masked. Limits/truncation and unavailable frames are explicit.
3. POST /contexts/{id}/model-input with {"goal":"trusted user task"} obtains provider-neutral input plus a strict decision schema. Pass this to the model adapter in core. Website content is explicitly untrusted; it cannot override system instructions, fill missing data or approve submission. Vision-capable providers can consume the screenshot; text providers can use the structured observation.
4. Parse ModelDecision: act, needs_information, needs_human, needs_review or done. Validate against the observation with validate_decision or GeneralBrowserClient.apply_decision. An act decision must reference a current observed target; other decisions cannot execute an action. No model provider is called by this service.
5. POST /contexts/{id}/actions with action_id, observation_id, kind and target_ref where required. Supported: click, fill, select (single/multiple values), check, upload, navigate, back, scroll, wait, switch_tab and extract. Values/uploads require verified=true and source_ref from trusted core. Never send OTP/passwords to the generic fill tool; auth-risk targets are refused.
6. Inspect the returned observation after each action. DOM/URL changes, stale generations, expired snapshots or closed contexts cause explicit errors. Do not invent a fallback selector. Ask core's model/skill system to reobserve/replan the broken step.
7. Pause for missing information/human verification/final review. Those dedicated operations need the corresponding trusted portal adapter; generic tools do not bypass them.

GeneralBrowserClient exposes create, observe, model_input, act, apply_decision and close. ModelPort is a provider-neutral protocol, not a default stub that pretends to reason. ModelDecision and action/start schemas are exported under contracts/v2. The actual full API surface is in contracts/v1/openapi.json and /openapi.json, including v2 paths.

Controls also include viewport bounds/in-viewport flags for screenshot-to-DOM grounding. Fill/select/check/upload results include explicit readback checks and field/source provenance; a successful transport response is not a claim that an entire application succeeded. Replayed action results are marked replayed=true and may contain old observations—reobserve before the next decision. Native dialogs are safely dismissed and reported by type, never automatically accepted. Baseline privacy filtering is not a guarantee that arbitrary real-page screenshots contain no sensitive information.

For a core graph node, GeneralBrowserClient.step_with_model(id, goal, model_adapter) performs exactly one caller-requested step. The adapter implements async decide(request=payload), receiving the complete trusted-goal/untrusted-observation/instructions/schema envelope. A missing adapter raises an error; there is no fake default decision. The result is validated and either safely executed or returned as a pause. This is not an autonomous agent loop or a bundled model provider.

## Artifacts, viewer and events

POST /contexts/{id}/artifacts accepts subject, source_ref, file_name, mime_type and file_base64 for validated PDF/PNG/JPEG up to 1 MB. Images get signature/dimension checks; artifacts are encrypted and bound to the context/subject. An upload action references artifact_id and is checked against the observed input's accept constraint. No arbitrary filesystem paths or fetch URLs are accepted.

GET /contexts/{id}/view returns a read-only frame without changing core's current observation/target mapping. /browser-workbench uses /api/browser-contexts/{id}/view through citizen/operator identity; the service key is never embedded in frontend code. GET /contexts/{id}/events supports a cursor. GET /contexts/{id} exposes generation/state; DELETE closes the worker and removes associated sensitive result/artifact data. Closed context tombstones keep request IDs from silently resurrecting old execution.

The viewer includes recent encrypted field/source provenance. Context results/artifacts are covered by cleanup and encryption-key rotation. For a live synthetic review context, run scripts/simulate_general.py with BASE_URL set to the running local app; it prints a viewer URL and explicitly makes no model call. The SDK tester runs on isolated ports 8920/8921, not production.

## Recovery and capabilities

Request/action IDs and unknown-outcome barriers persist in SQLite. Encrypted action results can be replayed. If the worker loses context, the gateway marks it lost and refuses stale execution. Create a fresh generation with a new request ID, perform necessary human login and let core replay only verified safe steps. Screenshot DOM refs are not persistent skills or checkpointed credentials.

GET /capabilities lists implemented observation/actions and operations that require dedicated adapters. AuthenticationAdapter, HumanRegionAdapter, ReviewAdapter, ReceiptAdapter, CoreSkillPort and VerifiedProfilePort are explicit trusted extension interfaces. They have no false-success default implementations. Production enablement, actual provider reasoning, real challenge compatibility, official submission/receipt adapters and external integrations are not claimed.

Verification: python scripts/verify_general_browser.py. It uses a separate synthetic workshop website with different field labels/controls, frames, shadow DOM, new tabs and review tables. A scripted controller chooses actions to verify tools; no AI reasoning is reported. INTEGRATION_AUDIT.md records the other prior shortcuts and their exact replacement/boundary.
