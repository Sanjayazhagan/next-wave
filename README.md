# GradientZero agent API

Core of the Forge '26 project: the LangGraph agent, WhatsApp channel, encrypted
vault, skill library and session API. See [contracts/README.md](contracts/README.md)
for how the other modules plug in.

## Run it locally

```bash
cp .env.example .env
uv sync
uv run pytest
uv run uvicorn --factory app.main:create_app --port 8000
```

Start the LLM proxy in a second terminal:

```bash
uvx --python 3.12 freellmpool==0.13.0 proxy
```

With `USE_STANDINS=true` the agent uses a fake portal and fake extraction. The
fake portal's OTP is `123456` and its CAPTCHA is `ABCD`.

## Deploy

The image runs the API and the freellmpool proxy in one container, and works on any
platform that sets `PORT`. It needs a persistent volume at `/data`, one instance
only, and no scale-to-zero: SQLite and the live event stream live in that instance,
and work continues after the webhook has been answered.

### Northflank

1. Create a combined service from this GitHub repo, using the `Dockerfile` as the build
   type and exposing port 8000 publicly over HTTP.
2. Add a volume to the service, mounted at `/data`.
3. Paste your `.env` into the service's runtime variables.
4. In Meta, under WhatsApp > Configuration, set the callback URL to the service's public
   address plus `/whatsapp`, paste `WHATSAPP_VERIFY_TOKEN`, and subscribe to `messages`.

Set `USE_STANDINS=false`, `BROWSER_WORKER_URL` and `LANGUAGE_SERVICE_URL` once those
services are up. Back up `VAULT_KEY` somewhere safe: without it the vault cannot be read.

### Region

This API works from any region. The browser worker is different: portals may refuse
traffic from outside India, so test them from its region first.

## Session API

Send the `X-API-Key` header with `API_TOKEN` on every call. For the event stream,
the browser's `EventSource` cannot set headers, so use `?key=` instead.

| Call | Purpose |
| --- | --- |
| `POST /session` | Start a session. Pass `{"phone": "91..."}` to link WhatsApp |
| `GET /session/{id}` | Status, paused prompt, masked profile with source tags, filled fields |
| `GET /session/{id}/events` | Live agent events (Server-Sent Events) |
| `GET /session/{id}/audit` | The full audit trail |
| `POST /session/{id}/reply` | Answer a prompt with `{"text": ...}` or `{"button": ...}` |
| `POST /session/{id}/files` | Upload a document |
| `POST /session/{id}/handover` | Helper resumes: `{"action": "resume"}`, `{"action": "abort"}`, or `{"receipt_number": ...}` |

## Safety rules built into the code

- **Personal data and the LLM:** the model sees field names and masked page text,
  never values. It names a field and the graph types the value locally.
- **Encryption:** the vault, uploaded files and LangGraph checkpoints are encrypted.
- **Final submit:** the model can never press it. It needs the user's approval, and
  `ALLOW_REAL_SUBMIT=true`. It defaults to false, which stops at the review page.
- **Double submit:** a restart can never submit twice. An unclear result goes to a helper.
- **Screenshots:** only sent to WhatsApp when the browser worker marks them masked.
