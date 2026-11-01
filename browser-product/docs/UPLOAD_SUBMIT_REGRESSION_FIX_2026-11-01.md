# Plain `submit` button in document upload form: regression fix (1 November 2026)

## Confirmed cause

The `/core-browser/session/{sid}/action` bridge previously saw a button named `submit` and applied the final-application authorization rule (403), even when this button belonged to a separate document-upload-only form. Sending an upload file through the API (`type: upload`, status 200) only attaches it to the browser input; it does **not** prove the portal received the file.

## Updated behavior

1. Every inspected form control now records the submitter's **effective form action URL** (`formaction` override if present, otherwise the parent form `action`), method, enctype and document-form association. Query strings are omitted from snapshot metadata.
2. A plain `Submit` or `submit` button is recognized as `upload_step` **only** when its own form contains a file input, contains no other user-entry fields, uses POST, points to a specifically named upload/file/document/attachment URL path, and does not describe a final application/registration submission.
3. That click requires **a file actually attached to this same form**, and enables **only an exact-target same-origin POST** for the duration of the click. It does not permit a site-wide POST wildcard. The browser's final-submission URL block still takes priority.
4. Buttons named `Submit Application`, an ambiguous Submit button in a mixed application form, and form actions that resemble `/submit`, `/payment`, `/approve`, etc. remain protected.
5. For other upload form layouts (AJAX uploads, mixed forms, paths not clearly upload-related), maintain the existing operator-reviewed origin requirement or use an explicitly reviewed portal adapter. Do not loosen the global POST permission to work around these cases.
6. Additive snapshot node fields: `form_method`, `form_action`, `dedicated_upload_form`, and existing `action_category`. The `document_upload_step` result reports `confirmed_by_portal: false`; **the core must re-snapshot and check actual portal confirmation.**
7. Numeric OTP inputs with labels such as `Code`, when next to an explicit `Verify OTP` control, are now `human_input` with `spinbutton` role. OTP contents stay human-only. `Refresh CAPTCHA` and clearly labelled CAPTCHA/security-code images are exposed to human assistance. Arbitrary CAPTCHA UIs remain unsupported without portal-specific validation.

## Direct live Azure test (no LLM tokens)

Keep your service base and key from the previous PowerShell session. Start a **new** core-browser session against the authorized test portal and use `GET /core-browser/session/{id}/snapshot` after login. The upload submit button should appear with:

```json
{"role":"button","name":"submit","action_category":"upload_step","dedicated_upload_form":true,"form_action":"https://example.test/upload","form_method":"post"}
```

The example hostname is fictitious. If `dedicated_upload_form` is false, do **not** force an unknown form's Submit button. Inspect its nonsecret form method/action and use a reviewed adapter. Next attach a synthetic document to the observed `fileupload` input, take a fresh snapshot, then `POST /core-browser/session/{id}/action` for the observed `submit` button. Re-snapshot and confirm the site's actual upload success message/file ID; `ok:true` alone is not proof. Never submit a real citizen application as part of this test.

For a 409 after the site changes, **take a new snapshot and replan**. Do not blindly replay the prior click because it may already have happened.

An intermittently failing session open has not been diagnosed. Capture timestamp, HTTP status, and sanitized worker logs if repeated. Do not assume it was a capacity issue.

## Rebuild existing Azure VM after updating GitHub branch

```bash
cd ~/next-wave/browser-product
git pull --ff-only origin feat/browser-product
sudo docker compose --env-file .env \
  -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml up -d --build
curl -fsS http://127.0.0.1:8100/ready
```

Keep `BROWSER_ENABLE_FINAL_SUBMIT=false` and `BROWSER_ALLOW_FORM_POST=false`. Neither your secret `.env` nor private SSH key belongs in the ZIP. This is a prototype; broad public-web browsing and real citizen portal transactions still require security auditing.

## Local validation

- `pytest -q tests/test_scoped_upload_submit.py`: dedicated file-only form, separate final-application form, exact scoped route, numeric OTP and CAPTCHA-image controls.
- The local CI runner blocks external and even loopback Chromium navigation (`ERR_BLOCKED_BY_ADMINISTRATOR`), so the test uses a real in-memory DOM submission handler plus a separate mocked request-router test. **A real HTTPS file POST on Azure has not yet been verified.**
- `pytest -q --ignore=tests/test_worker_flow.py --ignore=tests/test_core_compat_live.py --ignore=tests/test_interactive_control.py`: 70 passing (before final metadata/documentation sweep). The excluded legacy tests require a missing Playwright-bundled Chromium browser.
