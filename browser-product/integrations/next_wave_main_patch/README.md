# Tiny, optional patch to Sanjayazhagan/next-wave main (4 files)

The original `main` files are **not** modified in the Browser Product branch.
These are copies of **four** original files with targeted compatibility edits:

- `app/browser.py`: service-to-service `X-Internal-Key` header and `authorize_submit()` call.
- `app/config.py`: add `BROWSER_WORKER_KEY` setting.
- `contracts/browser.py`: optional `observation_id` binds approval to the visible page.
- `app/graph/nodes.py`: don't ask for portal login ID until an actual login field exists; explicitly authorize the final click **after** core's existing approval/duplicate-submit gate.

The rest of his LangGraph, LLM/planner, sessions, vault, checkpoints, skills,
channels, document pipeline, and API remain untouched. The core agent stays
in charge of page decisions; this patch does not replace or fork his agent.

## Apply only after reviewing the diff with main owner

From the extracted Browser Product repo root, back up and merge manually or
copy the four files into a **separate core feature branch**, not `main`:

```bash
# From the team's main checkout, on a fresh branch:
git switch -c feat/browser-integration
# Replace PATH_TO_BROWSER_PRODUCT with your extracted browser-product path
cp PATH_TO_BROWSER_PRODUCT/integrations/next_wave_main_patch/app/browser.py app/browser.py
cp PATH_TO_BROWSER_PRODUCT/integrations/next_wave_main_patch/app/config.py app/config.py
cp PATH_TO_BROWSER_PRODUCT/integrations/next_wave_main_patch/app/graph/nodes.py app/graph/nodes.py
cp PATH_TO_BROWSER_PRODUCT/integrations/next_wave_main_patch/contracts/browser.py contracts/browser.py
git diff --stat && git diff
```

Configuration on **main** API:

```ini
USE_STANDINS=false
DEFAULT_PORTAL_ID=your-reviewed-portal-id
BROWSER_WORKER_URL=https://browser.example/core-browser
BROWSER_WORKER_KEY=***same INTERNAL_KEY as browser service***
ALLOW_REAL_SUBMIT=false
```

The API uses header auth, **not** a secret in the URL. Do not store keys in Git.
`ALLOW_REAL_SUBMIT` must stay false until real portal adapters and approvals
are verified; an additional worker-side `BROWSER_ENABLE_FINAL_SUBMIT` defaults
false regardless of this main API setting.

### Source check / limitations

Based on the uploaded `next-wave-main.zip` at the time of this update. If main
has moved, **rebase these four changes manually**; do not overwrite his newer
changes with stale copies. Full core API test suite was not run here because
the host lacks several dependencies from his `pyproject.toml`. The isolated
browser implementation is separately tested.
