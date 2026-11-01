# Language service (M2)

A small FastAPI service for speech-to-text, translation and text-to-speech. Core
calls it for every voice note (`app/language.py`), with
`LANGUAGE_SERVICE_URL=http://<host>:8081`. Request and response bodies follow
[`contracts/language.py`](../../contracts/language.py); the extra fields below are
optional, and core ignores the extra response fields.

It uses Bhashini first and falls back to Sarvam (`LANG_PRIMARY` flips the order,
`STT_PRIMARY` overrides it for speech-to-text only). The primary gets one retry,
then the fallback is tried. If both fail, the reply is `503` with both errors.

## Endpoints

| Call | Body | Reply |
| --- | --- | --- |
| `POST /stt` | `{audio_base64, mime_type, language?}` | `{text, language, provider, latency_ms}` |
| `POST /translate` | `{text, source, target, keep?: [str]}` | `{text, provider, latency_ms}` |
| `POST /tts` | `{text, language, voice?}` | `{audio_base64, mime_type, provider, latency_ms}` |
| `GET /health` | | `{bhashini: {configured, ok, last_latency_ms}, sarvam: {...}}` |

- `/stt` takes any audio ffmpeg reads (Telegram OGG/Opus included) and converts it
  to 16 kHz mono WAV. Without a `language` hint it auto-detects (Sarvam); core uses
  the detected language for the rest of the session. Bhashini needs a language,
  so without a hint it uses `STT_DEFAULT_LANG`.
- `/tts` returns WAV. Core converts it to OGG/Opus for voice notes.
- `/translate` keeps rupee amounts, dates, ID-like tokens and every `keep` term
  intact: they are swapped for tokens `⟦0⟧, ⟦1⟧ ...` before translation and put
  back afterwards. If a provider drops a token, the other provider is tried; if
  both drop it, the original values are appended in brackets.
- Language codes are ISO 639-1 (`ta`, `en`, `hi` ...), the same as core.
- Logs (`$LOG_DIR/language.jsonl`) hold operation, provider, latency and input
  length only, never the text or audio.

```bash
curl -s localhost:8081/stt -H 'content-type: application/json' \
  -d "{\"audio_base64\": \"$(base64 -w0 fixtures/voice/1_scholarship.ogg)\", \"mime_type\": \"audio/ogg\"}"

curl -s localhost:8081/translate -H 'content-type: application/json' \
  -d '{"text": "Post Matric Scholarship gives ₹2,50,000", "source": "en", "target": "ta", "keep": ["Post Matric Scholarship"]}'

curl -s localhost:8081/tts -H 'content-type: application/json' \
  -d '{"text": "உங்கள் விண்ணப்பம் தயார்", "language": "ta"}' | jq -r .audio_base64 | base64 -d > out.wav

curl -s localhost:8081/health
```

## Run

```bash
uv run uvicorn modules.language.app:app --port 8081          # needs ffmpeg on the host

docker build -f modules/language/Dockerfile -t gz-language .  # from the repo root
docker run --env-file .env -p 8081:8081 gz-language
```

`compose_snippet.yml` has the service block for the main compose file.

### Deploy on Railway (next to the core API)

1. In the Railway project: **New service → GitHub repo** (this repo), name it `language`.
2. Service **Settings → Config-as-code**: `modules/language/railway.toml` (builds
   `modules/language/Dockerfile` from the repo root, health check `/health`).
3. Service **Variables**: `SARVAM_API_KEY` (and the `BHASHINI_*` three if used),
   `LANG_PRIMARY=sarvam` while Bhashini isn't configured. Railway sets `PORT`.
4. **Settings → Networking**: generate a domain, or use the private address
   `http://language.railway.internal:<PORT>`.
5. On the **core API** service, set `LANGUAGE_SERVICE_URL` to that address and redeploy.
6. Check: `curl https://<domain>/health` shows `"sarvam": {"configured": true, ...}`, and the
   core's `uv run python -m scripts.check_integration` shows the language service READY.

This service never calls Groq, so it doesn't need the core's shared LLM pacing.

Tested 1 Nov 2026: the image builds and runs locally; `/health` answers and a same-language
request works. A real translation answers 503 until a valid Sarvam key is set.

## Environment

| Variable | Purpose |
| --- | --- |
| `BHASHINI_USER_ID`, `BHASHINI_ULCA_API_KEY`, `BHASHINI_PIPELINE_ID` | Bhashini (ULCA profile page) |
| `SARVAM_API_KEY` | Sarvam |
| `LANG_PRIMARY` | `bhashini` (default) or `sarvam` |
| `STT_PRIMARY` | optional override for speech-to-text |
| `STT_DEFAULT_LANG` | Bhashini's ASR language when no hint is given (default `ta`) |
| `SARVAM_STT_MODEL`, `SARVAM_STT_MODE` | default `saaras:v3`; mode e.g. `codemix` |
| `SARVAM_TRANSLATE_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER` | defaults `sarvam-translate:v1`, `bulbul:v3`, provider default voice |
| `BHASHINI_TTS_GENDER` | `female` (default) or `male` |
| `PROVIDER_TIMEOUT_S`, `STT_TIMEOUT_S` | 5 and 15 seconds |

## Choosing STT_PRIMARY

Put a few real Telegram voice notes in `fixtures/voice/*.ogg` (git-ignored), then:

```bash
uv run python -m scripts.compare_stt
```

It prints each provider's transcript and latency per file, including Sarvam's
`codemix` mode, which writes English words in Latin script.

Decision (1 Nov 2026): **`STT_PRIMARY=sarvam` with `SARVAM_STT_MODE=codemix`**, and
`LANG_PRIMARY=sarvam` while Bhashini isn't configured. On three Tamil voice notes (made with
Sarvam's text-to-speech, so cleaner than real phone audio), code-mix mode wrote English words in
English ("Scholarship apply பண்ணணும்", "BE முதல் ஆண்டு") and amounts as digits ("₹2,00,000"),
and was faster (130-480 ms). Recheck with real voice notes when you have them.

## Provider docs used

- Sarvam (checked 31 Oct 2026): `POST https://api.sarvam.ai/speech-to-text`,
  `/translate`, `/text-to-speech`, header `api-subscription-key`.
- Bhashini (checked 31 Oct 2026): config call to
  `https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline` with
  `userID` and `ulcaApiKey` headers, then compute to the returned `callbackUrl`
  with the returned inference key header. Config is cached for an hour.
