# Codex handoff — real OTP/CAPTCHA and intermediate-action update

You may completely refactor or rewrite the browser code if this boilerplate is inadequate, but keep the requirements and safety guarantees. The user's newest explicit directions take precedence over this handoff; mandatory security controls are never optional. Do not alter teammate `main` without explicit authorization.

Read `docs/REAL_BROWSER_INTERMEDIATE_AND_HANDOFF.md`, `docs/AZURE_UPDATE_EXISTING_BROWSER.md`, `browser/step_policy.py`, `browser/core_compat.py`, `server/core_assist.py` and `deploy/Caddyfile`.

Current deliverables: intent classification, scoped OTP POST, bounded resend/verification, manually controlled upload-step, reviewed intermediate POST origins, short-lived assistance links with fragment tokens, human-only screenshot controls, explicit return to the agent, audit without OTP contents, UI, and tests.

**Mandatory remaining integrations**: run Docker and validate Caddy syntax/HTTPS, deliver assistance link to the real citizen via authenticated channel, test actual OTP and CAPTCHA on authorized portals, apply per-site POST review and final submission adapter, solve credential/session-recovery edge cases, perform robust threat modeling and egress isolation, load test, run the full test suite with bundled Chromium and live Azure.

Do not claim the new real-portal CAPTCHA handoff works until a real challenge is manually completed on the deployed browser and the agent safely resumes. The worker's generic final-submit path is not a finished real-portal adapter.
