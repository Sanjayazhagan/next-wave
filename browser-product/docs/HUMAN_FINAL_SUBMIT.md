# Citizen-operated final Submit handoff

The citizen can now click one reviewed final button through the existing
assistance page. Automated final submission remains disabled. This code does
not modify the teammate's bot/graph or prove that a citizen pressed Approve;
the trusted bot backend must verify and record that approval before issuing
the task. Never give the assistance capability to an LLM or use it as an
automated-submit API.

## Exact integration sequence

1. Get `GET /core-browser/session/{sid}/snapshot` with `X-Internal-Key`.
2. Show the review to the citizen and collect their explicit Approve tap.
3. Create the task using the observation ID of that reviewed snapshot and a
   unique consent/approval reference. Do not call `authorize-submit` for this
   separate manual flow. Poll task status while the person owns the browser;
   avoid refreshing browser snapshots underneath their live view.

```http
POST /core-browser/session/{sid}/human-task
X-Internal-Key: <backend service key>
Content-Type: application/json

{
  "reason": "submit",
  "review_observation_id": "<snapshot.observation_id>",
  "approval_ref": "<unique reference to the citizen's recorded approval>",
  "target_ref": "<ref of the reviewed final Submit node>",
  "ttl_seconds": 600
}
```

`target_ref` can be omitted only if exactly one enabled final control exists.
`review_observation_id` and `approval_ref` are required for submit tasks. Submit
tasks default to 600 seconds and accept 60–600 seconds; other task defaults
remain 300 seconds. All example identifiers below are placeholders.

```json
{
  "task_id": "<task UUID>",
  "expires_at": 1793500000.0,
  "assistance_path": "/core-assist/<task UUID>#<private capability>",
  "assistance_url": "https://browser.example.org/core-assist/<task UUID>#<private capability>",
  "reason": "submit",
  "single_use": true,
  "note": "Share the link only with the citizen; no WhatsApp message is sent automatically."
}
```

4. Send `assistance_url` to the citizen through the bot. The link opens the
   reviewed session with only the final Submit control. Typing, other website
   clicks, CAPTCHA coordinates and manual completion attestation are refused.
5. The citizen clicks Submit once. The page displays the observed outcome.
6. Poll `GET /core-browser/session/{sid}/human-task` with the backend key.

Example confirmed status (additional fields such as page text may be present):

```json
{
  "id": "<task UUID>",
  "task_id": "<same task UUID>",
  "session_id": "<browser session>",
  "reason": "submit",
  "state": "completed",
  "confirmed_by_portal": true,
  "receipt_number": "PRACTICE-123",
  "click_attempted": true,
  "request_observed": true,
  "needs_reconciliation": false,
  "url": "https://practice.example/receipt",
  "page_status": "ready",
  "page_text": "Application successfully submitted. Receipt: PRACTICE-123",
  "content_trust": "untrusted_website_data"
}
```

Python reference helper:

```python
task = await browser.human_task(
    sid, "submit",
    review_observation_id=review["observation_id"],
    approval_ref=citizen_approval_ref,
    target_ref=submit_node["ref"],
    ttl_seconds=600,
)
# Your bot sends task["assistance_url"] to the citizen, not to the model.
result = await browser.human_task_status(sid)
```

## Outcomes and recovery

- `active`: person has not completed their task; do not close the session.
- `submitting`: request claimed; never dispatch another click.
- `completed`: a scoped request and the configured portal receipt evidence were
  observed. The compatibility receipt parser requires an operator-supplied
  `receipt_pattern` and positive submission-success wording.
- `uncertain`: request may have executed but evidence/response is insufficient.
  This is not a failure-to-submit signal. Do not create another task, send a
  new action ID or retry submission. Inspect/reconcile the actual portal state.
- `review_changed`: no click was dispatched; get a fresh snapshot and a new
  citizen approval/reference. The old link is invalid.
- `expired`, `rejected`, `cancelled`: old link cannot be used. Establish actual
  session/task state before issuing a new approved workflow.

The API claims the token transactionally before worker dispatch. Completed and
uncertain task results survive API restarts in an encrypted, task-scoped table.
Polling can recover an authoritative late worker result after a lost response.
A worker crash cannot restore its browser context; an uncertain task remains
quarantined and must be reconciled. There is no cross-session exactly-once
application guarantee: do not reopen and resubmit an uncertain application.

## Review and execution safeguards

The worker binds the original observation ID, complete page fingerprint,
origin/URL, submit target and immutable field/file state. It rechecks before
displaying controls and immediately before dispatch. A changed page or expired
task is refused. Approval references cannot be reused. The capability becomes
unusable after the click is claimed, even if the response is lost.

An active bounded human lease protects the browser from idle cleanup and
ordinary session-close requests until completion/cancellation/expiry. A result
does not automatically close the context. Submit tasks cannot click through
authentication or CAPTCHA; complete those first through their existing tasks.
CAPTCHA remains a handoff-link feature; no cropped image delivery is included.

Only complete same-origin native GET/POST forms are supported by the manual
submit path. A one-request scope permits that exact reviewed form destination
during the human's click. This does not enable generic POSTs or change
`BROWSER_ENABLE_FINAL_SUBMIT=false`. Cross-origin or JavaScript-only submission
requires a reviewed portal adapter; it fails closed instead of claiming success.
Show the final control in the reviewed viewport where possible: changes caused
by a moving page/scrolling may conservatively require a fresh review.

## Azure public URL configuration

Use the existing API environment setting, for example:

```dotenv
DEMO_HOST=browser.your-domain.example
BROWSER_ENABLE_FINAL_SUBMIT=false
```

`DEMO_HOST` already passes through the existing Compose configuration. An
alternative is `PUBLIC_BASE_URL=https://browser.your-domain.example` when
explicitly provided to the API process. Use only a root HTTPS origin on port
443, with no credentials/query/path. Untrusted request Host headers are never
used to construct public links. Integrated/public deployments fail clearly
with 503 if the public origin is missing; they do not silently return a null
assistance URL. Isolated localhost demos can use their localhost base URL.

No environment, Compose, reverse-proxy, firewall or secret files were changed.
Keep ports 8100/8101 private and use the existing HTTPS proxy. The new
`core_assist_results` table is added lazily; existing SQLite tables/rows are not
rewritten. Results use the configured encryption keys and existing retention.
No capability token, receipt page body or secret is added to audit messages.

## Verification and remaining owner work

Run `python -m pytest -q` and `python scripts/verify_human_submit.py`.
The latter drives the actual mobile assistance page and worker against an
isolated local practice portal, verifies a receipt through bot polling, and
proves only one POST and a refused second click with automation disabled.

The existing CAPTCHA handoff check and a live public practice-upload check were
also run. These are local-host results, not Azure VM results. The teammate must
wire the Approve handler, forward the link, poll results and handle uncertainty.
The owner must commit/deploy and verify `git log -1 --oneline`, public HTTPS URL,
upload, consent and submit flows on practice portals from the deployed VM.
No new commit, push or deployment was performed here.

Validation evidence: full suite 149 passed; after the final preflight-expiry
guard, 17 focused submit/token tests passed, and the mobile UI end-to-end check
passed again. A final status-envelope correction passed its five API tests.
The new test count is larger because the expiry-during-preflight case was added
after the full run. The original CAPTCHA/mobile handoff passed unchanged.

The live practice-upload request accepted attachment and the Upload click but
returned empty confirmation text on that attempt. One bounded follow-up timed
out opening the portal (504). This pass does **not** claim a confirmed live
upload or Azure upload. Earlier successful local upload evidence does not
replace validation from the deployed VM.
