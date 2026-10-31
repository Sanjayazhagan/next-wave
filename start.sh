#!/bin/sh
# Starts the API, plus the freellmpool proxy when no hosted LLM is configured.
set -e

# Platforms mount volumes as root, so hand this one to the API's user.
chown -R 1001:1001 /data

case "${LLM_BASE_URL:-}" in
    ""|*localhost*|*127.0.0.1*)
        # Not 8080: platforms such as Railway give the API that port through PORT.
        PROXY_PORT=8090
        export LLM_BASE_URL="http://127.0.0.1:${PROXY_PORT}/v1"

        # The proxy is third-party code, so it gets its own user and none of the
        # app's secrets.
        (
            while true; do
                env -u WHATSAPP_ACCESS_TOKEN -u WHATSAPP_APP_SECRET -u WHATSAPP_VERIFY_TOKEN \
                    -u TELEGRAM_BOT_TOKEN -u TELEGRAM_WEBHOOK_SECRET \
                    -u VAULT_KEY -u API_TOKEN HOME=/home/pool \
                    setpriv --reuid=1002 --regid=1002 --clear-groups \
                    freellmpool proxy --host 127.0.0.1 --port "$PROXY_PORT" || true
                sleep 5
            done
        ) &
        ;;
esac

exec env HOME=/home/agent setpriv --reuid=1001 --regid=1001 --clear-groups \
    uvicorn --factory app.main:create_app --host 0.0.0.0 --port "${PORT:-8000}"
