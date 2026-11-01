# Local validation results — 2026-10-31

Tested the updated Browser Product **source** in this runner, with system Chromium available at `/usr/bin/chromium`.

```bash
python -m pytest -q --disable-warnings --ignore=tests/test_interactive_control.py --ignore=tests/test_worker_flow.py
# 66 passed, 1 skipped
node --check web/core_assist.js
# exit 0
python -m compileall -q browser server tests
# exit 0
```

The 2 excluded older files rely on the Playwright bundled Chromium executable, which is not installed here. The skipped network test cannot access its intended web host from this sandbox. The included integration tests use real **in-memory Chromium DOM** for OTP controls, human pause/resume, date/form context and upload discovery. There was **no real OTP or CAPTCHA solved**, no official site integration, no live Azure VM redeployment, and no Docker/Caddy runtime in this test container. Caddy syntax and live HTTPS assistance must be checked during your Azure update.

**Known limitations to re-test on Azure:**

- 2× OTP-send requests/10 min and ≤5 manual verify attempts/single session; test real portal resend/no account lockout.
- Exact-origin allowlist is required for agent-controlled intermediate POST; user-controlled upload POST is scoped to a single observed upload control.
- Screenshots may show sensitive page content to the citizen; use private, expiring assistance link, never forward to LLM.
- CAPTCHA click works on recognized iframe/image coordinates only; third-party provider flows may have additional restrictions or unsupported challenge controls.
- Human completion returns `verified: false`; core must inspect site and retry if the challenge remains.
- In-memory bridge state and pause state do not survive process restart; existing core session must be recreated/reconciled.
- No hardened egress proxy or verified anti-DNS-rebinding network firewall; do not grant untrusted users arbitrary public-web access.
- Final application submit remains protected and not generically proven on real sites.
