# Bridge repair release validation (31 Oct 2026)

Package scope: **browser-product only**, no teammate main files, no main patch or replacement `nodes.py`.

New behaviors:
- File inputs become `fileupload` nodes on `/core-browser/session/{sid}/snapshot`.
- Node names (consumable by old main `PageNode`) contain `accept`, required/multiple and nearby hint; rich additive fields are also present for newer clients.
- A `type=upload` action targeting a text input now fails 422; an input file receives bytes via Playwright's `set_input_files` with accept validation.
- `BROWSER_INTERMEDIATE_POST_ORIGINS` provides exact-origin operator review before allowing an intermediate POST in public-web browsing. This does **not** authorize final submit or verify that the POST is safe/nonirreversible.
- Navigation errors now distinguish timeout (504) and other failures (502); `scripts/diagnose_browser_navigation.py` outputs sanitized route and network failure evidence.

Local tests performed in the authoring environment:
- `python -m pytest -q --ignore=tests/test_worker_flow.py --ignore=tests/test_interactive_control.py`: **60 passed, 1 skipped**. The skipped test is an HTTP-based Chromium-to-localhost test blocked in this runner.
- `test_interactive_control.py`: **not run in the reported suite** because its Playwright browser executable is not installed in this runner.
- `test_worker_flow.py`: **not run in the reported suite**, same browser/runtime constraint as previous local baseline.
- New Chromium in-memory file upload and approval tests passed.
- Docker build, hosted public-site navigation, latest main LangGraph integration, real Heroku upload endpoint, actual external form POST, and multi-step actual government portal completion were **not executed here**.

**Operator validation required in Windows Docker:**

```powershell
# in browser-product, keep your existing .env
$env:BROWSER_INTERMEDIATE_POST_ORIGINS=''  # optional; usually leave empty

docker compose -f compose.yaml -f compose.integrated.yaml up -d --build
docker compose -f compose.yaml -f compose.integrated.yaml ps
Invoke-RestMethod http://localhost:8100/ready

docker compose -f compose.yaml -f compose.integrated.yaml exec worker python scripts/diagnose_browser_navigation.py https://the-internet.herokuapp.com/upload
```

Do not make a POST write authorization merely to get the test to pass. Use a reviewed practice site and separate citizen approval for irreversible actions.
