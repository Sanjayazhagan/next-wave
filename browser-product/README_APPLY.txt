Upload Submit Hotfix (2026-11-01)

Extract archive in the root of your local next-wave Git checkout.
It contains browser-product/ paths and only the changed files.
Do not overwrite .env; this patch contains no .env.

From repo root: git switch feat/browser-product
Then: git add browser-product
      git diff --cached --check
      git commit -m "fix(browser): scope upload-only submit buttons and OTP/CAPTCHA fields"
      git push origin feat/browser-product

SSH into Azure VM:
cd ~/next-wave/browser-product
git pull --ff-only origin feat/browser-product
sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml up -d --build
curl -fsS http://127.0.0.1:8100/ready

See browser-product/docs/UPLOAD_SUBMIT_REGRESSION_FIX_2026-11-01.md.
