# Browser bridge fixes — feedback from the main agent team (Oct 31 2026)

**Only `browser-product/` has changed. The teammate's latest `main` has NOT been modified or merged.** The older main snapshot (`next-wave-main.zip`) is not necessarily current. Previous patches that copied `nodes.py` are deliberately **removed** from this release. Do not apply an old patch or overwrite `app/graph/nodes.py`.

## Problems and response

1. **File upload appears as textbox in main.** Fixed in the core-compat bridge. An observed `input[type=file]` returns role `fileupload`, `element_type=file`, accepted extensions/MIME, required/multiple flags and bounded nearby page hints, both in the additive node fields and inside the `name` string that older `PageNode` models already expose to the planner. The browser action rejects uploads targeted at non-file controls and checks observed `accept` constraints. The core still must supply document data and provenance. More elaborate file-size/pixel rules require a document-preparation service and portal-specific policy.
2. **Heroku upload page timeout.** No root cause established by the screenshot. `POST /core-browser/session` and v2 context creation now return a `504` on navigation timeout instead of opaque `500`. Run the read-only probe inside **the worker container**; do not presume CORS, bot protection, or network failure without its result:

   ```powershell
   docker compose -f compose.yaml -f compose.integrated.yaml exec worker python scripts/diagnose_browser_navigation.py https://the-internet.herokuapp.com/upload
   ```

   The probe prints sanitized failed request URLs, HTTP status (if available), and elapsed time. If `current_page` is populated but navigation timed out, inspect response and DOM readiness; if requests fail, inspect DNS/TLS/route policy. No automated retry of POST or irreversible action.
3. **Multi-step forms POST on Next/Save.** Added `BROWSER_INTERMEDIATE_POST_ORIGINS`. For read-only discovery, leave it empty. The operator may explicitly configure e.g. `BROWSER_INTERMEDIATE_POST_ORIGINS=https://testpages.eviltester.com` **after reviewing the target form** and restart Docker. This permits POST only on that exact origin, while irreversible submission URL patterns and final submit clicks remain blocked. It is a pragmatic, still-imperfect site-level gate: real portals may use a generic `/submit` even for steps, or mutate state with `GET`/JavaScript; require site-by-site inspection. Do not set `BROWSER_ALLOW_FORM_POST=true` in public-web mode as a wildcard.
4. **Main patch no longer applies.** Do NOT replace core files. Core owner should work against **his latest branch** with localized edits: `app/browser.py` adds `X-Internal-Key` to authenticated browser requests and optional dynamic URL opening; `contracts/browser.py` can add optional `fileupload` metadata fields to `PageNode` and optional page-text fields to `Snapshot`; `app/planner.py` can render those extra fields, but existing main sees the most important upload metadata in node `name` already. Keep existing LangGraph nodes and business logic intact. Tests must run against his checked-out branch, not this uploaded snapshot.

## Quick compatibility checks

- `/core-browser/session/{id}/snapshot` exposes `role=fileupload` for an actual file input and preserves existing `url`, `title`, `nodes`, challenge/error/receipt keys.
- `/core-browser/session/{id}/action` accepts `upload` for an observed `fileupload`, with `file_base64`, `file_name`, `file_mime`, and requires an appropriate artifact from core.
- No direct model execution in browser worker; LangGraph remains the planner.
- Generic final submission remains off by default; OTP/CAPTCHA remain human-controlled.
- Valid read-only public URLs still work without per-site `.env` changes.

## What remains unproven

- The teammate's latest `main` API/graph integration (only an earlier snapshot is present).
- Live upload on `the-internet.herokuapp.com` from the teammate's network, and final submission on any real portal.
- Mumbai VM deployment, real government portal authorization, and full WhatsApp journey.
