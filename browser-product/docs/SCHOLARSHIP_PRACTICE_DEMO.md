# Mock scholarship demo and submission UI fixes

Based on the updated local checkout at commit `4fafd42`. Its CAPTCHA-link
guidance, submission-confirmation rules and privacy filtering were preserved.
No teammate language/eligibility/document-extraction modules were changed.

## Replace Selenium in the live preview

The API now serves a clearly labelled fictional form at:

```text
https://<your-browser-host>/practice/scholarship
```

It accepts synthetic name/email, age, income, course and an explicit synthetic
data checkbox. Submission produces a signed `DEMO-SCH-...` receipt. It stores
no applicant fields and makes no real scholarship application or eligibility
decision. The receipt page includes `Application successfully submitted` and
`Receipt: DEMO-SCH-...`, which the existing receipt parser can validate.

Merge the example in `deploy/practice-scholarship.example.json` into the
worker's existing `BROWSER_PORTALS_JSON`, replacing `YOUR-BROWSER-HOST`. Do not
overwrite other entries or any existing secrets. Example for the documented
Azure hostname:

```dotenv
BROWSER_PORTALS_JSON={"scholarship_practice":{"url":"https://gradientzero-browser26.eastasia.cloudapp.azure.com/practice/scholarship","receipt_pattern":"Receipt: (DEMO-SCH-[A-F0-9]{12}-[A-F0-9]{32})"}}
BROWSER_ENABLE_FINAL_SUBMIT=false
```

If the bot already opens a portal ID such as `test`, change that existing
entry's URL and receipt pattern instead, keeping the ID unchanged. Otherwise
the bot owner should select `scholarship_practice`. Open the **configured ID**:

```http
POST /core-browser/session
X-Internal-Key: <backend key>
Content-Type: application/json

{"portal_id":"scholarship_practice"}
```

A direct dynamic `url` open does not automatically inherit a registered
portal's receipt pattern. In allowlist navigation mode, also permit the exact
public browser origin in `BROWSER_ALLOWED_ORIGINS`. Public-web mode keeps its
existing HTTPS/DNS restrictions. Do not point the deployed public-web worker
at a loopback/private URL. No new public port is needed.

Fill only the supplied synthetic data. The checkbox needs explicit verified
input, as before. Collect the citizen's Approve, create the existing submit
human task and send its `assistance_url`. The human clicks Submit once.
`GET /core-browser/session/{sid}/human-task` then reports the observed demo
receipt and `confirmed_by_portal: true`. The checkbox and the final approval
are separate decisions; neither is inferred by the browser.

## Timer and status behavior

- Submit completion, an uncertain response, a failed control request, ordinary
  handoff completion and expiry clear/hide `#expiry`; no frozen last value.
- Refresh is disabled after the task ends. Delayed successful or failed preview
  requests cannot restore the countdown, controls or overwrite receipt feedback.
- After Submit, the earlier review screenshot is hidden so an old form is not
  presented as a live preview of the post-submission page.
- A confirmed result shows `Submission confirmed` and the real receipt number.
  A confirmed portal without a receipt explicitly says none was provided.
- An unconfirmed result shows `Submission outcome uncertain`, not `Submission
  requires review`. A changed review is separately labelled `New review required`.
  Unknown/transport outcomes never imply success or authorize another click.

The new receipt is valid only for the fictional practice form. Selenium's
narrow receipt-free confirmation rule remains supported for regression tests;
no confirmation policy was weakened or replaced with URL-only guessing.

## Validation and deployment

```text
python -m pytest -q
python scripts/verify_scholarship_demo.py
```

The second command runs real API/worker services and a mobile assistance page
using a temporary database and made-up profile. It fills the form, performs
human approval/Submit, validates the receipt in bot polling and verifies the
timer is hidden and empty. It does not call Telegram or a real scheme.

Deploy the source update using your normal feature-branch process, merge the
portal registry entry, and recreate the API/worker services. This local change
does not alter `.env`, SQLite/runtime data, TLS/firewall configuration or remote
bot selection. Azure was not redeployed or verified by this task.
