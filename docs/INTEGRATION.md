# Plugging into the agent

Everything here plugs in without changing the agent. To see what is connected and what
is wrong, run this from the repo root:

```bash
uv run python -m scripts.check_integration
```

It prints `READY`, `not yet` or `FAILED` for each part, and says what to fix. **If your
part shows READY, it works in the agent.** To test extraction on a real document:

```bash
uv run python -m scripts.check_integration --document path/to/marksheet.jpg
```

`contracts/` is the one source of truth. The schemas in `browser-product/contracts/`
differ in places, so build to `contracts/`. See [the differences](#contract-differences).

## Remote teammate: modules

Add one file per module under `modules/` with the function below, and open a pull
request. That is all. Core imports it on startup, and each function can be sync or async.

| # | File | Function | Input and output |
| --- | --- | --- | --- |
| 1 | `modules/extraction.py` | `extract(images)` | `list[DocumentImage]` → `ExtractionResult` |
| 3 | `modules/compressor.py` | `fit_file(data, mime_type, portal_id, document_type)` | `bytes` → `bytes`. Optional better compression: core then fits the result to each form's own rules. |
| 4 | `modules/rules.py` | `rank_schemes(request)` | `EligibilityRequest` → `EligibilityResponse` |
| 5 | `modules/doctor.py` | `check_application(request)` | `DoctorRequest` → `DoctorResponse` |

For example, this is a complete rule engine that plugs in:

```python
from contracts.eligibility import EligibilityRequest, EligibilityResponse, SchemeMatch


def rank_schemes(request: EligibilityRequest) -> EligibilityResponse:
    income = int(request.profile.fields["annual_income"].value)
    if income > 250000:
        return EligibilityResponse(schemes=[])
    return EligibilityResponse(schemes=[
        SchemeMatch(
            scheme_id="post-matric",
            name="Post-Matric Scholarship",
            portal_id="nsp",
            rank=1,
            cited_clause="Clause 3.1: family income under 2.5 lakh",
        )
    ])
```

Rules for every module:

- **Field names:** use the names in `FIELD_NAMES` in `contracts/profile.py`. Ask on a sync
  call before adding one.
- **Values:** in English, with `annual_income` as digits only, such as `120000`.
- **Time:** a module gets 120 seconds. After that it is skipped.
- **Failure:** if a module crashes or returns the wrong shape, the agent skips that step
  and carries on, so a user is never stuck. Its error shows in the checker.
- **Personal data:** never log or print document contents, Aadhaar or bank numbers.
  `Mismatch.detail` is shown to the user, so it must not repeat those numbers.

Core checks the user's answers before these run. `extract` runs after the documents
arrive, and a user's confirmed answer wins over a document, so the doctor should flag
any clash rather than change a value.

### 2. Language service

This is an HTTP service. Set `LANGUAGE_SERVICE_URL` on the server and it switches on.

| Route | Request | Response |
| --- | --- | --- |
| `POST /stt` | `SttRequest` | `SttResponse` |
| `POST /translate` | `TranslateRequest` | `TranslateResponse` |
| `POST /tts` | `TtsRequest` | `TtsResponse` |

Audio is base64 JSON. `/tts` can return any format ffmpeg reads, because core converts it
to a voice note. Voice notes then flow into the AI chat, and the receipt is spoken.

### 6 and 7. Chaos script and benchmark

- **Chaos script:** runs through the browser service's `inject` command.
- **Benchmark:** drive the agent through the session API in the README.

## Browser teammate: Pranav

The service in `browser-product/` is already connected. Two settings choose the mode:

| `BROWSER_PRODUCT_MODE` | Uses | For | Connector |
| --- | --- | --- | --- |
| `portal` | v1 API | The fictional portal, end to end with OTP, CAPTCHA and a receipt | `app/browser_product.py` |
| `general` | v2 API | Real pages step by step, with skills and self-repair | `app/browser_general.py` |
| `bridge` | `/core-browser` | Live pages: login, OTP and CAPTCHA go to the user, and the final submit needs an approval tied to the page shown | `app/browser_bridge.py` |

To connect it, deploy the service, then set `BROWSER_PRODUCT_URL` and
`BROWSER_PRODUCT_KEY` (its `INTERNAL_KEY`) on the server.

For each real portal:

1. Add its origin to `BROWSER_ALLOWED_ORIGINS` on the service, once you have confirmed
   that automating it is allowed.
2. Add its start page to `PORTAL_URLS`, such as `{"nsp": "https://scholarships.gov.in/"}`.
3. Build the portal's login, challenge, review and submit adapters. v2 refuses those
   controls until a reviewed adapter exists, and without one the agent hands over to a
   helper. **This is the main remaining work.**
4. Tell core how to reach those adapters. `app/browser_general.py` is where they connect.

Also needed:

- **Hosting:** the service needs a server with enough memory for Chromium, and possibly
  an Indian location. Confirm that portals load from there.
- **Document uploads:** forms differ, so no form's rules are in the code. Core reads them
  from the form, in this order, and sends a file unchanged if it already fits:
  1. The control's `accept` list, label and description, or the `upload` entry in the
     service's portal catalog. A browser worker reports these in `PageNode.file_rules`.
  2. The page text. The model copies the words that apply to that control, code checks
     they are really on the page, and code reads the numbers.
  3. The service's own ceiling, in `Snapshot.upload_limits`. In `general` mode this is PDF,
     JPEG or PNG up to `BROWSER_UPLOAD_MAX_BYTES`, because the service refuses more.
     **Pranav:** if you raise your 1 MB limit, raise that setting to match.

  Core can convert JPEG, PNG, WebP, HEIC, PDF and Word `.docx` files. A `.docx` keeps its
  words, tables and images but not its exact layout. It is refused if it holds a chart,
  an embedded object, or a language no font on the server can print. Old `.doc` files
  are not supported.
- **Web app:** set `CORS_ORIGINS` on the server, and use the session API in the README. It
  takes `X-API-Key`. The event stream takes `?key=`.

## Contract differences

Build to `contracts/`. The agent ignores extra fields, so these are the ones that matter:

| Interface | `contracts/` | `browser-product/contracts/` |
| --- | --- | --- |
| Language | Three routes: `/stt`, `/translate`, `/tts`, with base64 audio | One `operation` field, with `audio_ref` |
| Agent events | `type`, `message`, `at` | `event_type`, `summary`, `timestamp` |
| Doctor | `allowed_to_continue` is optional | It is required |
| Browser | `contracts/browser.py` | Connected through the two connectors above |

## Merging

1. Build on your own branch from `main`, and only touch your own files.
2. Run the checker and `uv run pytest`.
3. Open a pull request.
4. Core deploys with `railway up --service api`, then runs the checker against the server's
   settings.
