# Extraction (M1)

Reads phone photos (JPG, PNG, HEIC) or PDFs of Indian certificates and fills the
profile. Core loads it through `app/plugins.py`:

```python
async def extract(images: list[DocumentImage]) -> ExtractionResult
```

Each upload is one document, classified as `marksheet`, `income` or `community`
(`other` is returned with no fields). `ExtractedDocument.file_ref` is core's id
for the original upload, so core can still find the file to attach to the portal.

Fields it fills: `full_name`, `father_name`, `institution`, `course`,
`year_of_study`, `marks_percent`, `exam_year`, `annual_income`, `community`,
`district`, `state`, `certificate_number`, `issue_date`, `aadhaar_last4`.
Values are strings: dates as `YYYY-MM-DD`, income as digits, community as a short
code (`BC`, `MBC`, `SC`, ...).

## Confidence is agreement, not the model's opinion

```
confidence = 0.6 * agreement + 0.4 * valid
```

- `agreement`: best fuzzy match (`rapidfuzz.partial_ratio`) between the text the
  model says it read the value from and any Tesseract OCR line, or two adjacent
  lines for values that wrap. Tesseract is independent of the model, so a high
  score means two different readers saw the same text.
- `valid`: 1 if the value passes `validators.check` (name characters, age 14 to 60,
  marks 0 to 100, known community code, issue date after 2000 and not in the future).

A field under 0.6 gets one retry: its region is cropped with 40 px padding,
upscaled 2x and read again. The better-scoring reading wins.

## Pipeline

| Step | File |
| --- | --- |
| Load pages: EXIF rotation, HEIC, PDF at 200 dpi | `preprocess.load_pages` |
| Find the paper (largest 4-sided contour, perspective transform) | `preprocess.find_document` |
| Deskew (Otsu + `minAreaRect`, when 0.5° < skew < 15°) | `preprocess.deskew` |
| Blur and brightness check | `preprocess.quality` |
| OCR, `eng+tam` | `ocr.read_words` |
| **Mask Aadhaar and bank numbers, before saving or any LLM call** | `mask.redact` |
| Classify, then one vision call with a per-type schema | `classify.py`, `schemas.py`, `prompts.py` |
| Score each field, retry weak ones | `confidence.py`, `pipeline.py` |
| Convert to contract types, merge into a profile | `merge.py` |

Masking: 12-digit Aadhaar numbers (even when OCR splits them over 3 words) and
9 to 18 digit account numbers after `A/c`, `Account` or `SB` are blurred on the
image, and only the last 4 digits are kept. `mask.mask_text` is a second guard on
every value and evidence string the model returns.

If one upload can't be read (bad file, model error), it is skipped with a log line
and the run carries on; the eligibility questions cover the missing fields.

## Setup

```bash
sudo apt install tesseract-ocr tesseract-ocr-tam   # also needed in the Docker image
uv sync
```

`.env`: `LLM_BASE_URL` and `LLM_API_KEY` (shared with core) and `VISION_MODEL`, a
vision-capable model on that endpoint.

```bash
uv run python -m modules.extraction.cli fixtures/docs/a_marksheet.jpg --type marksheet
```

## Thresholds

| Constant | Value | File |
| --- | --- | --- |
| `BLUR_MIN` | 60 | `preprocess.py` (TODO(satyajit): tune on real fixtures) |
| `BRIGHTNESS_MIN` | 60 | `preprocess.py` (TODO(satyajit): tune on real fixtures) |
| `RETRY_BELOW` | 0.6 | `pipeline.py` |

## Accuracy

Put real documents in `fixtures/docs/<stem>.jpg` and their true values in
`fixtures/ground_truth/<stem>.json` (`{"doc_type": "income", "fields": {...}}`).
`fixtures/` is git-ignored. Then:

```bash
uv run pytest -m live tests/test_extraction_accuracy.py -s
```

This writes `reports/extraction_accuracy.json`.

Overall field accuracy: [[NUMBER: from reports/extraction_accuracy.json]]
