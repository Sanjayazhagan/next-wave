# Browser complaints audit — local test evidence (2026-11-01)

Source: most recent reviewed browser-product code package generated from the uploaded `next-wave-browser-update.zip`, plus the changes described in `CAPTCHA_HANDOFF_AND_LIVE_CHECKS_NOV01.md`.

## Fixed in this source update

- `GET /core-assist/` now returns a safe public information page, instead of 404. Real session access still requires the task-specific token from the fragment-backed invitation URL. Caddy route matcher explicitly includes the bare path and the task paths.
- Browser compatibility snapshots now advertise CAPTCHA/OTP `challenge.delivery_mode = human_assistance_link`, `human_task_reason`, `requires_human = true`, and `image_base64 = null`, without exporting page images to Telegram. Iframe-only challenge signals also produce an explicit CAPTCHA challenge.
- Updated reference Python client pauses for an explicit CAPTCHA handoff even when a website's page status is `blocked`, while leaving `inspection_incomplete` paused.
- Existing scoped upload form POST and final application submission protections were not broadened.

## Tests completed locally

- **99 passed** in the runnable API/policy/helper/non-network subset; no failures in that selection.
- **8 passed** in a targeted subset including the local DOM upload-only Submit behavior and permission scoping plus the new human-assistance/CAPTCHA-link tests.
- Full test command started but hit `net::ERR_BLOCKED_BY_ADMINISTRATOR` on a Playwright navigation test in this host. This is **not** an Azure test result, and the complete browser E2E suite was not validated here.
- Python bytecode compilation, JavaScript syntax check for `web/core_assist.js`, Bash syntax validation, and Compose YAML parse passed.

## Must still be checked outside this environment

- New code is not committed, pushed or deployed to Azure by this process. After deploying, run `scripts/check_azure_browser_release.sh` from the Azure checkout. It checks the Git hash, running container source hashes, health, automated submission disabled, public port mappings, and the new bare `/core-assist/` HTTP 200.
- A new actual task-specific CAPTCHA/OTP assistance link must be opened, used and polled on an authorized practice site. A 200 landing page alone is **not** proof that task control works.
- File attachment plus clicking Upload **and verifying the practice portal itself accepted the document** has not been reproduced on the live Azure deployment by this process. Earlier local synthetic upload tests do not substitute for this.
- The teammate must update bot code to handle `delivery_mode=human_assistance_link` and to create/send/poll the task; a bot that only looks for `challenge.image_base64` will not work until updated.
- `49ed519` is only an earlier expected commit. The most recent user-reported matching Azure/GitHub commit was `f770c8f`, which predates this uncommitted patch. Recheck after deploying.

Keep `BROWSER_ENABLE_FINAL_SUBMIT=false` and do not publicly expose TCP 8100/8101. Avoid posting service keys, capability fragments, private screenshots, or real citizen data in reports.
