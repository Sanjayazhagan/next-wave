# GradientZero agent API

Core of the Forge '26 project: the LangGraph agent, chat channels, encrypted vault,
skill library and session API. See [contracts/README.md](contracts/README.md) for how
the other modules plug in.

The live chat channel is Telegram: [@Dakiya_seva_bot](https://t.me/Dakiya_seva_bot).
The WhatsApp channel is built too, but Meta only delivers real messages to published
apps, and publishing needs business verification.

## Run it locally

```bash
cp .env.example .env
uv sync
uv run pytest
uv run uvicorn --factory app.main:create_app --port 8000
```

The bot uses Groq by default, so set `LLM_API_KEY` to a Groq key. To use the free
keyless proxy instead, set `LLM_BASE_URL=http://localhost:8080/v1` and `LLM_MODEL=auto`,
then start it in a second terminal:

```bash
uvx --python 3.12 freellmpool==0.13.0 proxy
```

With `USE_STANDINS=true` the agent uses a fake portal and fake extraction. The
fake portal's OTP is `123456` and its CAPTCHA is `ABCD`.

## Deploy

The image runs the API, plus the freellmpool proxy when `LLM_BASE_URL` points at
localhost, and works on any platform that sets `PORT`. It needs a persistent volume at `/data`, one instance
only, and no scale-to-zero: SQLite and the live event stream live in that instance,
and work continues after the webhook has been answered.

### Railway

Live at `https://api-production-be3b1.up.railway.app`. To redeploy from this folder:

```bash
railway up --service api
```

To set it up from scratch:

1. Run `railway login`, `railway init --name next-wave` and
   `railway add --service api`, then `railway service link api`.
2. Run `railway volume add --mount-path /data`. From Git Bash, use PowerShell instead,
   because Git Bash rewrites the path.
3. Copy your `.env` into the service's variables, then run `railway domain`.
4. Set `PUBLIC_URL` to that address. With `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_WEBHOOK_SECRET` also set, the server registers its Telegram webhook when
   it starts.
5. For WhatsApp, in Meta under WhatsApp > Configuration, set the callback URL to that
   address plus `/whatsapp`, paste `WHATSAPP_VERIFY_TOKEN`, and subscribe to `messages`.
   The app must be published before real messages arrive.

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

- **AI chat:** the model handles the conversation and the basic eligibility details,
  with ID-shaped text masked first. If it fails, the fixed questions take over.
- **Sensitive steps:** OTPs, CAPTCHAs, logins, documents and approval stay in fixed
  code and never reach the model.
- **Portal planning:** the model sees field names and masked page text, never values.
  It names a field and the graph types the value locally.
- **Encryption:** the vault, uploaded files and LangGraph checkpoints are encrypted.
- **Final submit:** the model can never press it. It needs the user's approval, and
  `ALLOW_REAL_SUBMIT=true`. It defaults to false, which stops at the review page.
- **Double submit:** a restart can never submit twice. An unclear result goes to a helper.
- **Screenshots:** only sent to WhatsApp when the browser worker marks them masked.
