# Dakiya: an agent that applies for scholarships, not one that explains them

> Team GradientZero · Forge '26, Theme 1 (Civic Pulse) · "Autonomous Public Service and Bureaucracy Execution Agent"

[[GIF: Tamil voice note on Telegram → cited scheme → form filling itself → review screenshot]]

## The problem

Students in Tamil Nadu who qualify for scholarships often never apply. Finding the
right scheme means reading dense guidelines; applying means a portal in English,
document uploads with strict size limits, and rejections over small mismatches
(an initial on one certificate, a full name on another). Chatbots can describe
schemes. They don't fill the form.

## What it does

1. **Ask in your language.** Send a Tamil voice note to the Telegram bot. It's
   transcribed (Bhashini, with Sarvam as fallback) and answered in Tamil.
2. **Find schemes you qualify for**, with the rule and its official source quoted.
3. **Read your documents.** Photos of your marksheet, income and community
   certificates fill your profile; every field shows which document it came from.
4. **Catch rejection risks first.** The application doctor flags name mismatches,
   missing documents and conflicting values, with one fix each.
5. **Fill the portal form.** A browser agent logs in and fills it, replaying a saved
   skill and repairing itself when the page changes. CAPTCHA and OTP go to you on
   Telegram; it never bypasses them.
6. **Submit only after you approve** the review page, and get the receipt in Tamil.

[[SCREENSHOT: user flow, 6 steps]]

## Architecture

```mermaid
<paste docs/architecture.mmd>
```

## What makes it different

- **Skill replay and self-repair.** The first run explores the portal and saves the
  steps; later runs replay them. When a label or layout changes, the agent finds
  the field again and saves the repaired skill.
- **Tested against chaos.** `modules/chaos/chaos.js` breaks the page on purpose
  (renamed labels, rewrapped and reordered fields, hidden sections, popups, slow
  network), repeatably by seed, without touching what the server depends on.
- **Eligibility you can check.** Plain Python rules, no LLM at decision time. Each
  rule file is scraped from the official page, and a rule loads only after a person
  reviews it and only if its clause appears verbatim in the scraped source.
- **Confidence that means something.** A field's confidence is agreement between
  the vision model and independent OCR, plus a validity check, not the model's
  opinion of itself.
- **An application doctor**: a transparent points checklist, not a black-box score. It catches expired
  certificates and name mismatches, and **flags tampered TN e-District certificates** by comparing the QR
  code with the printed number and name.

## Setup

```bash
cp .env.example .env        # fill in the keys you have
uv sync
uv run pytest
uv run uvicorn --factory app.main:create_app --port 8000
uv run uvicorn modules.language.app:app --port 8081        # language service
```

System packages: `ffmpeg`, `tesseract-ocr`, `tesseract-ocr-tam`. Each module has its
own README under `modules/`.

## Results

| Config | Runs | Success | Median seconds to review |
| --- | --- | --- | --- |
| Dakiya, first run (explore) | [[NUMBER]] | [[NUMBER]] | [[NUMBER]] |
| Dakiya, replay | [[NUMBER]] | [[NUMBER]] | [[NUMBER]] |
| browser-use baseline | [[NUMBER]] | [[NUMBER]] | [[NUMBER]] |

Document extraction field accuracy: 94.7% (18 of 19 fields on 3 real certificates; small sample) [[NUMBER: update after more documents]].
Benchmark runs stop at the review page; nothing is submitted. [[NUMBER: say which portal the runs used]]

## Guardrails and privacy

- Aadhaar and bank numbers are masked on the image before it's saved or sent to any
  model; only the last 4 digits are kept.
- No CAPTCHA, OTP or face-authentication bypass: those go to the citizen.
- Nothing is submitted without the citizen's explicit approval of the review page.
- Personal data is encrypted in the vault; documents sent over Telegram are deleted
  from our storage after 30 days. [[CONFIRM: retention job is implemented in core]]
- Logs hold lengths, field names and timings, never document text or personal values.

## Data sources

| Source | Used for |
| --- | --- |
| myscheme.gov.in (psgs-deg, sak-deg, pudhumai-penn-scheme, pmstn) | scheme eligibility rules |
| bcmbcmw.tn.gov.in/welfschemes.htm | TN post-matric scholarship rules |
| scholarships.gov.in | National Scholarship Portal |
| Bhashini (ULCA) and Sarvam AI APIs | speech, translation, text-to-speech |

## Team

| Member | Role |
| --- | --- |
| [[NAME]] | Core: gateway, LangGraph orchestrator, vault, skill library |
| [[NAME]] | Browser worker, portal flows, web app, deployment |
| Satyajit | Extraction, language service, rule engine, doctor, compressor, chaos, benchmark |
