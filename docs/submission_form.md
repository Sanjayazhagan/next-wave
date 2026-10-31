# Submission form text

## Problem statement
Students who qualify for government scholarships often never apply. Eligibility
rules are buried in long guidelines, portals are in English, uploads have strict
size and format limits, and applications are rejected over small mismatches between
documents. Existing chatbots explain schemes but leave the citizen to fight the portal.

## Target audience
Students in Tamil Nadu (and later other states) applying for central and state
scholarships, especially first-generation applicants more comfortable in Tamil than
English, and NGOs or e-Sevai operators who apply on their behalf.

## High-level solution
Dakiya is an agent on Telegram that applies for scholarships. A student sends a Tamil
voice note; Dakiya asks a few questions, finds the schemes they qualify for with the
official rule quoted, reads photos of their certificates, flags rejection risks, and
fills the government portal form with a browser agent that replays saved steps and
repairs itself when the page changes. CAPTCHA, OTP and the final approval stay with
the student. Others explain schemes. We apply for them.

## Technical architecture
- **Stack:** Python 3.12, FastAPI, LangGraph (orchestration with pause and resume),
  Playwright (browser worker), SQLite (sessions, skills, encrypted vault), Telegram
  Bot API, Docker.
- **Models:** an OpenAI-compatible LLM endpoint (Groq, `qwen/qwen3.8-27b` for text and
  document images); Bhashini and Sarvam AI for speech-to-text, translation and
  text-to-speech; Tesseract OCR as an independent check on document reading.
- **Data sources:** official scheme pages on myscheme.gov.in and the Tamil Nadu BC/MBC
  welfare department, scraped with timestamps and hashes; the National Scholarship
  Portal.
- **System design:** a Telegram gateway feeds a LangGraph orchestrator. Plug-in
  modules handle document extraction (vision model checked against OCR, ID numbers
  masked before any model sees them), eligibility (plain-Python rules that load only
  after human review and only if each clause is verbatim in the official source),
  the application doctor (transparent points checklist, including a tampering check that compares a TN
  e-District certificate's QR code with its printed number and name) and file compression to
  portal limits. A Playwright worker drives the portal through accessibility roles
  and names; a chaos script tests self-repair. Every step is streamed to a web app
  and recorded in an audit trail.
