#!/bin/sh
# Runs the LLM proxy beside the API, on loopback so only this container reaches it.
set -e

# Not 8080: platforms such as Railway give the API that port through PORT.
PROXY_PORT=8090
export LLM_BASE_URL="http://127.0.0.1:${PROXY_PORT}/v1"

# Platforms mount volumes as root, so hand this one to the API's user.
chown -R 1001:1001 /data

# The proxy is third-party code, so it gets its own user and none of the app's secrets.
(
    while true; do
        env -u WHATSAPP_ACCESS_TOKEN -u WHATSAPP_APP_SECRET -u WHATSAPP_VERIFY_TOKEN \
            -u VAULT_KEY -u API_TOKEN HOME=/home/pool \
            setpriv --reuid=1002 --regid=1002 --clear-groups \
            freellmpool proxy --host 127.0.0.1 --port "$PROXY_PORT" || true
        sleep 5
    done
) &

exec env HOME=/home/agent setpriv --reuid=1001 --regid=1001 --clear-groups \
    uvicorn --factory app.main:create_app --host 0.0.0.0 --port "${PORT:-8000}"
