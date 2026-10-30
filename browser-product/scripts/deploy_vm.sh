#!/usr/bin/env bash
# Launches a TLS/password-gated synthetic demo on an ALREADY PROVISIONED Mumbai VM.
# No cloud resources are created; this does not authorize government portal automation.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null; then
  echo 'ERROR: Docker is required on the VM. Follow docs/DEPLOY_MUMBAI.md.' >&2; exit 1
fi
if [[ ! -f .env ]]; then
  echo 'ERROR: .env missing. Copy .env.vm.example to .env and set secrets.' >&2; exit 1
fi
for var in DEMO_HOST ACME_EMAIL DEMO_USER DEMO_PASSWORD_HASH INTERNAL_KEY APP_SIGNING_KEY; do
  if ! grep -Eq "^${var}=.{4,}" .env; then
    echo "ERROR: ${var} must be set in .env" >&2; exit 1
  fi
done
if grep -Eq 'REPLACE_WITH|your-domain\.example|your-email@example\.org|demo-worker-key-change|demo-signing-key-change' .env; then
  echo 'ERROR: placeholder/demo credentials detected. Refusing to deploy.' >&2; exit 1
fi
if [[ -n "$(grep -E '^APP_MODE=' .env | grep -v '^APP_MODE=demo$' || true)" ]]; then
  echo 'ERROR: This repo only implements APP_MODE=demo.' >&2; exit 1
fi

docker compose --env-file .env -f compose.yaml -f compose.vm.yaml config --quiet

docker compose --env-file .env -f compose.yaml -f compose.vm.yaml up -d --build --remove-orphans
docker compose --env-file .env -f compose.yaml -f compose.vm.yaml ps

echo 'Checking API health via VM-local, loopback-bound port ...'
if curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 2 http://127.0.0.1:8100/health; then
  echo
  echo 'API health reached. Next: manually verify https://<DEMO_HOST> using browser + Basic auth.'
  echo 'MANDATORY DAY-1 CHECK: run portal_reachability.py from the worker container and save output.'
  echo 'NOTE: This is only an API check; it does not validate the complete Playwright application flow.'
else
  echo 'ERROR: API did not become healthy; inspect docker compose logs.' >&2
  exit 1
fi
