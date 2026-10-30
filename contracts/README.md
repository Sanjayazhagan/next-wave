# Contracts

Frozen interfaces between the three of us. Change one only on a sync call.
Each file holds Pydantic models; `Model.model_json_schema()` gives the JSON Schema.

| Interface | File | Between |
| --- | --- | --- |
| Profile schema | `profile.py` | Extraction → core → doctor |
| Extracted document schema | `documents.py` | Extraction → core |
| Eligibility I/O | `eligibility.py` | Rule engine ↔ core |
| Doctor I/O | `doctor.py` | Doctor ↔ core |
| Agent events | `events.py` | Core → web app, chat channels, benchmark |
| Language API | `language.py` | Language service ↔ core |
| Chaos inject | `browser.py` (`InjectRequest`) | Chaos script ↔ browser worker |
| Vault calls | `vault.py` | Core ↔ vault |
| Snapshot and actions | `browser.py` | Core ↔ browser worker |

## Plugging in a module

Add a file under `modules/` with the function below. It can be sync or async.
Core imports it on startup. If the file is missing, core carries on without it:
the rule engine and doctor nodes are skipped, and extraction leaves the profile
to the eligibility questions.

| File | Function |
| --- | --- |
| `modules/extraction.py` | `extract(images: list[DocumentImage]) -> ExtractionResult` |
| `modules/rules.py` | `rank_schemes(request: EligibilityRequest) -> EligibilityResponse` |
| `modules/doctor.py` | `check_application(request: DoctorRequest) -> DoctorResponse` |
| `modules/compressor.py` | `fit_file(data: bytes, mime_type: str, portal_id: str, document_type: str) -> bytes` |

The language service and browser worker are HTTP services. Set
`LANGUAGE_SERVICE_URL` and `BROWSER_WORKER_URL` to connect them.

## Rules for personal data

- Never log or put Aadhaar numbers, bank numbers, OTPs or CAPTCHA answers in
  events, exceptions or skill files.
- `Mismatch.detail` is shown to the user and in the audit trail, so it must not
  repeat those numbers.
- Set `screenshot_masked` only when the screenshot really has them blanked out.
