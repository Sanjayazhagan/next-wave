# Browser human-submit outcome reconciliation (November 2026)

## Confirmed defect and fix

In the Azure Selenium practice run, the human clicked Submit once, the browser reached
`https://www.selenium.dev/selenium/web/submitted-form.html`, and the page displayed
`Form submitted` and `Received!`. Nonetheless `/core-browser/session/{sid}/human-task`
returned `uncertain` because the earlier code **required a receipt number**. Selenium's
practice form does not issue one.

The fixed browser worker considers a manual submission **completed without a receipt**
only when there is independently reviewed portal success evidence:

- A real form request was observed during the one allowed human click;
- The page changed from the approved review and the resulting page status is ready;
- Either a vetted receipt pattern matches a success confirmation (existing behavior),
  **or** an exact source + exact confirmation URL **and** all required literal phrases match.

The Selenium public practice form is the single built-in no-receipt rule. It is exact;
other websites cannot claim success by copying its message. All other no-receipt
workflows remain `uncertain` until an operator supplies an explicit portal rule.

`completed` now includes `outcome: portal_confirmed`, a `confirmation_evidence`
label and `receipt_number: null` when the portal does not issue a receipt. No receipt
is invented. Status responses no longer include raw confirmation-page text, which
might contain personal information. Confirmation URLs in status have query and
fragment removed. Browser *snapshots* can still include page text for the
backend's controlled verification, but it must not be indiscriminately forwarded
into bot conversations.

## Optional operator-reviewed rules

Only add this for an authorized practice portal, or a real portal after a human
reviews and tests its successful outcome. Add to the Azure VM's existing `.env`:

```dotenv
BROWSER_SUBMIT_CONFIRMATIONS_JSON=[{"source_url":"https://practice.example.org/apply","success_url":"https://practice.example.org/receipt","required_text":["Application received","Confirmation"]}]
```

The value must be valid JSON: a list (max 32) with **exact** keys `source_url`,
`success_url` and `required_text` (one to five literal phrases). Both pages must
have the same HTTPS origin. No wildcards, userinfo, fragments, arbitrary regex,
or cross-origin redirects. `http://127.0.0.1:<port>` is accepted only in
non-signed local **demo** mode, for synthetic tests.

The worker must receive this environment variable. The update includes it in
`compose.integrated.yaml`. Rebuild/recreate the containers after deploying.
**Never** change `BROWSER_ENABLE_FINAL_SUBMIT=false` or expose 8100/8101 publicly.

## Verification

Local unit tests:

```bash
python -m pytest -q tests/test_submit_confirmation.py tests/test_human_submit_reconciliation_unit.py tests/test_submit_task_api.py
```

Browser end-to-end tests (requires unrestricted Chromium + the test server):

```bash
python -m pytest -q tests/test_human_submit.py
python scripts/verify_human_submit.py
```

On Azure after pushing/redeploying, use a **fresh Selenium test session**, approve
its reviewed Submit node, click exactly once via the secure `core-assist` link,
and poll `GET /core-browser/session/{sid}/human-task`. Expected:

```json
{"state":"completed","confirmed_by_portal":true,"receipt_number":null,
 "confirmation_evidence":"reviewed_confirmation","outcome":"portal_confirmed"}
```

This is a **practice form** result, not a government receipt. If state is
`uncertain`, do not retry. Inspect the subsequent snapshot `page_text`, and
investigate the action outcome through the existing secure reconciliation path.

The bare `/core-assist/` now shows a safe informational page (HTTP 200, no session access). A valid handoff still requires `/core-assist/{task_id}#<capability>` and must remain secret.

## Boundaries

This patch does **not** solve arbitrary CAPTCHA widgets, automatically extract
CAPTCHA images for Telegram, verify arbitrary portal receipts, or deploy itself.
Real site-by-site success detection and final delivery through the agent still
require integration/acceptance testing. Do not forward full screenshots to
Telegram when they may contain applicant information.
