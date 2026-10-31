# Compressor (M3)

Makes a document file fit a portal's upload limits while keeping it readable.
Core loads it through `app/plugins.py` and calls it while attaching a file:

```python
def fit_file(data: bytes, mime_type: str, portal_id: str, document_type: str) -> bytes
```

For the details (what was done, whether it still reads), use
`prepare_for_portal(data, portal_id, document_type) -> Result(data, info: PreparedFile)`.

## Portal specs

Limits live in [`contracts/portals/<portal_id>.json`](../../contracts/portals/)
(`contracts.portal.PortalSpec`). Each limit says where it came from in
`source_note`. A `doc_type` of `"*"` applies to every document on that portal.

| portal_id | Limits | Source |
| --- | --- | --- |
| `mock-scholarship` | PDF, ≤ 1024 KB | browser teammate's demo portal (`browser/adapters.py`) |
| `nsp`, `tn_scholarship` | TODO(satyajit): not verified yet | none; see below |

**Limits are never guessed.** If a portal or document has no spec, `fit_file`
returns the file unchanged and logs a warning.

## What it does

1. If the file already has an accepted type and fits, it's returned untouched.
2. Photos are cropped to the paper and deskewed (same code as extraction).
3. Format: keep the source format if the portal accepts it, otherwise PDF if PDF
   is the only option, else JPEG, else PNG. (Core labels the upload with the
   original MIME type, so keeping the format avoids a mislabelled file.)
4. Downscale to `max_px` (and to at most 2400 px, about A4 at 200 dpi).
5. Binary search the JPEG quality in [35, 95] for the largest file under `max_kb`.
   If quality 35 is still too big, scale down (estimated from the size at quality
   35, at least 15% per step) to a minimum width of 800 px, then try grayscale. If it
   still won't fit, `CannotFit` is raised (`fit_file` then sends the original, and
   the doctor's file check flags it).
6. PDFs stay multi-page; all pages share the quality, with 8 KB kept for PDF overhead.
7. Under `min_kb`, quality is raised towards 95; if it's still small, the action
   "below portal minimum size, check manually" is added.
8. Legibility: confident Tesseract words (conf > 60) before and after.
   `legible = words_after >= 0.8 * words_before`; pages with fewer than 10 words
   are not judged.

`actions` explains it for the web app, for example
`["cropped", "deskewed 3.2°", "converted to PDF", "resized 4032x3024 to 2400x1786", "1840 KB to 182 KB (quality 71)"]`.

## CLI

```bash
uv run python -m modules.compressor.cli photo.jpg --portal mock-scholarship --doc-type income
```

## Tests

`tests/test_compressor.py`. The fixture test runs every file in `fixtures/docs/`
against every spec in `contracts/portals/` and skips when there are no fixtures.
