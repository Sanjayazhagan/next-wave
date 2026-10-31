# Submission-ready copy and 6-slide deck narrative

*This is written as a demo prototype. Update every technical claim after actual E2E verification and core-team integration.*

## Problem statement

Government services often rely on complex, non-API legacy portals that impose language, authentication, documentation and navigation hurdles. Citizens may not know eligibility requirements, document formats or whether their application reached a valid final state. The hackathon's Track 1, Problem 3 calls for an autonomous public-service browser agent to ingest a citizen’s background and requested service, navigate these portals, handle interface obstacles and produce tracked receipts.

## Solution

**GradientZero CivicFlow** is a citizen-controlled application assistant. It will combine deterministic scheme eligibility, sourced/document-checked information, a Playwright browser worker, pause/resume around user-only authentication, field provenance, live screen monitoring, explicit final review, audited form submission and follow-up status alerts. The browser teammate's current runnable prototype demonstrates these patterns on a **fictional scholarship portal**, including user-provided mock OTP and challenge, label-drift repair, popup and transient-error recovery, human takeover, a review-bound approval capability, synthetic receipt and status. The full Tamil WhatsApp/LangGraph/real portal workflow is integration work, **not a proven feature of this archive**.

## Technical architecture

User web console and eventually WhatsApp → LangGraph core (external teammate) → typed profile and document evidence (remote teammate) → FastAPI browser gateway → private Playwright worker → only authorized portal adapters → verified review → explicit user approval → receipt/status. Stream screenshots and masked audit events to the operator console. No CAPTCHA/OTP/Aadhaar authentication bypass; retain only minimal information and apply retention controls.

## Six slide outline with on-slide copy

1. **Why the last mile fails** — Complex forms, Tamil-language barriers, changing portal layouts, rejected documents, opaque status.
2. **The product: CivicFlow** — Ask in Tamil → Eligibility → Document doctor → Browser agent → Review approval → Receipt/status. One citizen, one connected journey.
3. **The technical differentiation** — Accessibility-first automation + evidence-backed fields + resilient step repair/checkpoints + explicit human gates + visual audit.
4. **Architecture & ownership** — Web/WhatsApp → Core LangGraph → Browser/Playwright → Approved portals; remote extract/eligibility/language modules; event stream/receipts.
5. **Live demo** — Mock scholarship start → user OTP/challenge → chaos label drift → repair → review → approval → simulated receipt + status. State explicitly “Fictional portal demonstration.”
6. **Proof, limitations & roadmap** — Show real 5-run benchmark after executing; what is tested vs not; portal permission and account walkthroughs; OIDC/vault/India VM/production hardening.

## Demo scorecard to fill with evidence

| Metric | Evidence needed | Current status |
|---|---|---|
| Mock browser complete runs | `python scripts/benchmark.py --runs 5` | Not run end-to-end in this execution environment |
| Semantic drift repair | DOM Playwright unit test output | Proven with synthetic alternate label |
| OTP/CAPTCHA human pauses | Worker unit and full integration | Worker in-memory test passed; end-to-end pending |
| Unapproved Submit blocked | Worker invalid capability test | Passed in-memory |
| Source tags and audit UI | Browser screenshot / operator walkthrough | Implemented code; live integrated UI pending |
| Real public portal end-to-end | Authorized real user + 5 runs each | **0 / not implemented** |
| Deployment | Container health, India region endpoint | Docker files created; deployment not performed |

## Differentiator claim for judges

“Rather than only answering which scheme to apply for, our design targets the difficult last mile: a traceable browser application that stops for citizen-only authentication, repairs a changed form element, verifies the evidence against the review page and never irreversibly submits without explicit citizen approval. The current demo proves the interaction pattern on a controlled synthetic portal; real deployment needs site-specific permission, reliability tests and security hardening.”
