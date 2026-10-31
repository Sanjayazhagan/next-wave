# Deck text (6 slides)

## 1. Team
**GradientZero · Dakiya**
- "Others explain schemes. We apply for them."
- Forge '26 · Theme 1: Civic Pulse
- [[NAME]] · [[NAME]] · Satyajit

Visual: Telegram chat bubble with a Tamil voice note, bot logo.

## 2. Problem
**Qualifying isn't the same as applying**
- Discovery: dozens of schemes, rules buried in long guidelines
- Language: portals in English, citizens speak Tamil
- Portals: OTP logins, strict upload limits, layouts that change
- Rejections over small mismatches: "S Satyajit" vs "Satyajit S"

Visual: a real portal screenshot with the pain points circled. [[SCREENSHOT: portal]]

## 3. Solution
**Six steps, one chat**
Voice note → cited schemes → document reading → **doctor** → **self-repairing form fill** → approve and receipt
- Highlighted: **skill replay and self-repair**, **chaos-tested**, **cited, reviewed rules**, **application doctor**
- The citizen handles only OTP, CAPTCHA and the final approval

Visual: 6-step strip, the four differentiators in colour.

## 4. Architecture
**Plain code where it must be right, AI where it helps**
- LangGraph orchestrator pauses for the citizen and resumes exactly where it stopped
- Replay and repair: saved skills replay; a changed field is found again and the skill re-saved
- Eligibility: reviewed rules, verbatim clauses, no LLM at decision time
- Doctor: transparent checklist, one fix per finding

Visual: docs/architecture.mmd rendered.

## 5. Results and roadmap
**Measured, not claimed**
- [[NUMBER: chart from results/chart.png: success rate and time to review, ours vs browser-use]]
- Extraction accuracy 94.7% on real certificates (18/19 fields) [[NUMBER: update]]; [[NUMBER]] self-repairs under chaos
- Tampered certificate caught: QR code vs printed number
- Next: more portals, DigiLocker documents, NGO operator mode, application status watcher

Visual: results/chart.png.

## 6. Demo summary
**Try it: @Dakiya_seva_bot**
- [[SCREENSHOT: voice note]] [[SCREENSHOT: cited schemes]] [[SCREENSHOT: doctor finding]]
  [[SCREENSHOT: form filling]] [[SCREENSHOT: CAPTCHA on Telegram]] [[SCREENSHOT: receipt]]
- Guardrails: masked IDs · no CAPTCHA/OTP bypass · approval before submit · auto-delete
- Links: [[LINK: live app]] · [[LINK: GitHub]] · [[LINK: video]] · QR code to the bot

Visual: 6 thumbnails, guardrails strip, QR code.
