# Update the EXISTING deployed Azure browser (no reinstall)

Target: `https://gradientzero-browser26.eastasia.cloudapp.azure.com`, Azure East Asia. This differs from the original team plan's Mumbai VM.

## 1. On Windows: update only feature branch

Extract the ZIP in a temporary location. It has **only `browser-product/`**, no teammate main, no `.env`, no runtime data, no cache directories. Copy it over the existing repository's `browser-product/` without deleting that directory's `.env`. Examine `git status` and `git diff`; stage `browser-product/` only, commit and push to `feat/browser-product` (do not force-push or merge `main`).

```powershell
cd C:\Users\asus\next-wave-browser-update
# after copying updated source, NOT your .env:
git switch feat/browser-product
git status --short
git add -A -- browser-product
git diff --cached --stat
git commit -m "feat: scoped OTP, intermediate actions and real-browser human takeover"
git push origin feat/browser-product
```

## 2. On Azure Ubuntu VM

```bash
cd ~/next-wave/browser-product
# Your .env exists only on the VM; keep it untouched.
git pull --ff-only origin feat/browser-product
sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml config --quiet
sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml up -d --build
sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml ps
curl -fsS http://127.0.0.1:8100/ready
```

Confirm HTTPS, the `/core-assist/` landing page (HTTP 200 with **no** browser/session content), a **generated** `/core-assist/{task_id}#token` invitation, and that only 80, 443 and restricted SSH 22 are open inbound. Do not expose 8100/8101. Keep `BROWSER_ENABLE_FINAL_SUBMIT=false`. The root landing page is not a valid CAPTCHA link.

**To optionally enable reviewed intermediate POSTs** for a specific authorized target, set `BROWSER_INTERMEDIATE_POST_ORIGINS=https://exact-portal-origin` in `.env` and recreate the worker via the three-file Compose command. Without this review, OTP-request controls can still use their narrowly scoped auth writes, but generic agent-controlled Next/Save/Upload POSTs remain restricted.

## 3. Secure live testing

From a trusted client with the server-side `INTERNAL_KEY`:

```http
POST https://gradientzero-browser26.eastasia.cloudapp.azure.com/core-browser/session
X-Internal-Key: ...
Content-Type: application/json

{"url":"https://www.selenium.dev/selenium/web/web-form.html","consent_ref":"authorized-test-2026"}
```

Record `session_id`. Snapshot and fill synthetic values, then create a human task only when an OTP/CAPTCHA/upload handoff is needed. Open its `assistance_url` on another trusted device. Confirm final Submit stays blocked without a reviewed adapter and explicit approval. Close the session afterward.

## 4. Rollback

If a health or security regression appears, redeploy the previous **known-good commit** on your feature branch. Do not force-push or alter `main`. Keep encrypted storage volumes and `.env` intact. SSH in and run the previous Compose command after checking out the earlier commit in a detached deployment worktree.

## 5. Credit reminder

Azure student VM consumes credits while running. Use **Stop (deallocate)** when finished, and check any persistent disk/IP charges. An auto-shutdown schedule can interrupt a live browser session; coordinate with teammate's test period.
