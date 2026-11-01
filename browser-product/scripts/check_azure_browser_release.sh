#!/usr/bin/env bash
# Run on the Azure Ubuntu VM from the existing browser-product checkout.
# Reports only public commit IDs, port bindings and health; never prints secrets.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=(sudo docker compose --env-file .env -f compose.yaml -f compose.vm.yaml -f compose.integrated.yaml)

echo '=== Commit ==='
git log -1 --oneline
printf 'GitHub cached tip: '; git rev-parse --short origin/feat/browser-product
printf 'Azure checkout:    '; git rev-parse --short HEAD

echo '=== Containers ==='
"${COMPOSE[@]}" ps

echo '=== API readiness ==='
curl -fsS --max-time 10 http://127.0.0.1:8100/ready; echo

echo '=== Running source matches checkout ==='
api_host=$(sha256sum server/core_assist.py | cut -d' ' -f1)
api_image=$("${COMPOSE[@]}" exec -T api sha256sum /app/server/core_assist.py | cut -d' ' -f1)
worker_host=$(sha256sum browser/core_compat.py | cut -d' ' -f1)
worker_image=$("${COMPOSE[@]}" exec -T worker sha256sum /app/browser/core_compat.py | cut -d' ' -f1)
if [[ "$api_host" != "$api_image" || "$worker_host" != "$worker_image" ]]; then
    echo 'ERROR: a running container does not match this checkout. Rebuild/recreate it.' >&2
    exit 1
fi
echo 'API and worker source hashes match.'

echo '=== Safety ==='
"${COMPOSE[@]}" exec -T worker sh -c 'test "${BROWSER_ENABLE_FINAL_SUBMIT:-false}" = false'
echo 'Automated final submission is disabled.'
api_ports=$("${COMPOSE[@]}" port api 8000)
case "$api_ports" in
  127.0.0.1:8100) echo "API host binding: $api_ports (localhost-only)" ;;
  *) echo "ERROR: unexpected API port binding: $api_ports" >&2; exit 1 ;;
esac
worker_ports=$(sudo docker port "$("${COMPOSE[@]}" ps -q worker)")
if [[ -n "$worker_ports" ]]; then
    echo "ERROR: worker has published host ports: $worker_ports" >&2
    exit 1
fi
echo 'Worker has no published host ports.'

echo '=== Assistance bare-route check ==='
status=$(curl -sS --max-time 12 -o /dev/null -w '%{http_code}'   'https://gradientzero-browser26.eastasia.cloudapp.azure.com/core-assist/')
echo "HTTP $status (expected 200 for information page, not an active invitation)"
[[ "$status" == '200' ]] || exit 1

echo 'CHECKS OK. The actual CAPTCHA link, Telegram integration, and external portal upload still need live functional tests.'
