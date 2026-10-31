# Chromium loading timeout workaround (31 Oct 2026)

## Observed problem

The upload test page `https://the-internet.herokuapp.com/upload` returned HTTP 200, but Chromium did not finish loading the first parser-blocking JS file. Without a workaround: `document.readyState=loading`, `document.body` absent, `DOMContentLoaded` timed out. Python `httpx` fetched JS files with HTTP 200. Standalone Chromium launched with `--disable-http2` reached DOMContentLoaded and found two file inputs. The evidence supports an HTTP/2-path problem for this test site but does not prove a universal root cause.

## Workaround

In `browser-product/.env`, append:

```dotenv
CHROMIUM_DISABLE_HTTP2=true
```

Then rebuild/recreate the worker with:

```powershell
docker compose -f compose.yaml -f compose.integrated.yaml up -d --build --force-recreate worker
```

The `browser.worker` Playwright launch reads the setting and includes `--disable-http2` when enabled. The diagnostics script uses the same flag. No API/client/agent changes are required. Existing browser sessions are lost if the worker restarts; do this outside an active workflow.

## Verification

```powershell
docker compose -f compose.yaml -f compose.integrated.yaml exec -T worker python -m scripts.diagnose_browser_navigation https://the-internet.herokuapp.com/upload
```

Expect `problem: null`, `page_has_body: true`, and `main_status: 200` if the workaround works in the routed browser. Repeat the Selenium form fill test and check logs for regressions.

This is a **selective compatibility workaround**: HTTP/2 is not malicious or inherently broken, and disabling it can reduce performance on other sites. Only turn it on for reproducibly affected workloads; turn it off to compare results (`false`). It does not grant the agent permission to submit forms, solve CAPTCHA, bypass OTP, or evade portal restrictions.
