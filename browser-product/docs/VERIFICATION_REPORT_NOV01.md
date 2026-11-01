# Browser source audit and confirmation repair — local verification

**Input:** user-supplied `next-wave-browser-update.zip` (contains repository snapshot and files).

**Root cause addressed:** Human final-submit completion demanded a nonempty `receipt_number`. Selenium's documented practice form confirms with `Form submitted` and `Received!` at an exact URL but issues no receipt; thus live Azure polling incorrectly remained `uncertain` even when the page confirmed success.

**Changes:**

- `browser/submit_confirmation.py`: exact, reviewed post-click evidence, including the one Selenium practice rule; optional per-portal reviewed literal evidence; never use URL change alone.
- `browser/human_submit.py`: use evidence for `completed` vs `uncertain`; preserve single use and no automatic retries; report `receipt_number=null` for confirmed no-receipt practice results; avoid copying page text or query strings into durable bot task outcome.
- `compose.integrated.yaml`, `.env.example`: thread optional `BROWSER_SUBMIT_CONFIRMATIONS_JSON` into the worker; default `[]`.
- New focused tests and an API-polling regression test.

**Tests executed in this environment**

- `python -m pytest -q tests/test_submit_confirmation.py tests/test_human_submit_reconciliation_unit.py tests/test_submit_task_api.py`: **30 passed**.
- Wider browser-free/API/security selection (`19` test modules): **64 passed** (includes the focused tests).
- `python -m compileall -q browser server clients scripts tests`: passed.
- `node --check web/core_assist.js` and `node --check browser/dom_census.js`: passed.
- PyYAML parse of the three Compose overlays: passed; API remains host-bound to `127.0.0.1:8100` and worker has no published host port.
- Source-release package ZIP integrity and secret-path exclusion checks: passed.

**Limitations:** Full Playwright tests and HTTP end-to-end tests could not be completed here. Playwright's default headless-shell is absent; using `/usr/bin/chromium` starts the browser but this environment returns `net::ERR_BLOCKED_BY_ADMINISTRATOR` on even synthetic localhost and `data:` navigation. This is an execution-environment blocker, **not evidence that Azure passed or failed**. Prior 149-pass report in the uploaded documentation is not a new independent test result.

**Required acceptance test after Azure deployment:** Use a fresh Selenium practice session, human-reviewed submit task and single manual click, then poll. Expected `state=completed`, `confirmed_by_portal=true`, `receipt_number=null`, `outcome=portal_confirmed`, `confirmation_evidence=reviewed_confirmation`. The previous `uncertain` task must not be retried. Confirm the upload-only practice POST separately and keep automatic final submission disabled.

**Known boundaries:** No claim of solving arbitrary CAPTCHAs or proving real government portal receipts. Existing CAPTCHA is human-link-only; it does not send cropped CAPTCHA images to the bot. Arbitrary custom widgets and uncertain outcomes continue to require reviewed portal adapters or manual reconciliation. Live Azure/Telegram integration was not accessed.

**Packaging:** The ZIPs generated here exclude uploaded `.env`, `.git`, private keys, caches and runtime/output data. Never overwrite the VM's existing `.env` or SQLite volume during redeployment.
