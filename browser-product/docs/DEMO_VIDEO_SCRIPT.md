# 2–3 minute demo script (browser teammate recording)

**Prerecording checklist:** First confirm with `scripts/smoke.py` and 5 consecutive successful mock runs. Keep the terminal and dashboard open. DO NOT display actual IDs, OTPs or confidential tabs. Use synthetic profile and fictional portal only, visibly labeled. Record 16:9 at 1080p; browser zoom around 90%. Test screen stream refresh; silence desktop notifications. Have a failure-free fallback pre-recording in addition to live run.

**0:00–0:15 — Problem and promise**: “Millions of citizens deal with confusing government forms. Our public-service agent can help them prepare an application, navigate a legacy portal, and keep a traceable record. This demonstration uses a fictional scholarship portal, not a real government service.” Show GradientZero mission control.

**0:15–0:35 — Consent and human authentication**: Click Start demo. Enter the fictional OTP `246810` and answer the manual mock human check `7`. Say: “Real OTP, CAPTCHA and Aadhaar device verification are completed by the person. Our agent never bypasses them.” Show screenshot updates.

**0:35–1:12 — Portal disruption / repair**: On form, click Chaos → Rename a field and Inject a popup. Show the actual browser screenshot. Click Auto-fill. Watch semantic locator fallback repair the income field, dismiss popup, attach synthetic document and reach review. Mention source tags, field-level checks and repair counter. “It re-checks the changed step instead of starting over.”

**1:12–1:40 — Verification and control**: Point to field evidence and audit timeline. “The system compares each reviewed portal value with verified inputs. The agent cannot click Submit without explicit approval.” Wait on review screen, then click the citizen approval button.

**1:40–2:02 — Receipt and status**: Show the mock receipt ID, click Check simulated status, open PDF receipt. Repeat “fictional receipt, not government-issued.”

**2:02–2:25 — Resilience and safe failure**: Short prepared clip: click Expire login in a second test, show human sign-in required again and checkpoint retained. Or click Hide income and show human takeover after three genuine attempts. This demonstrates fail-closed behavior.

**2:25–2:45 — What is real / what remains**: Show portal research sheet and architecture slide. “We verified the browser control and product flow against our deterministic sandbox. Official portal flows require authorized accounts and compliance with specific OTP/face-auth workflows.” Mention how core LangGraph and remote eligibility/document services plug in.

**No overclaims**: Never call the bundled application an official scholarship or claim you submitted on NSP. If real portal automation is later completed under authorization, clearly label the additional clip with site, permissions and actual action performed.

## Quick rehearsal QA

- [ ] 5 mock runs pass (report exact counts)
- [ ] Screen shows one clear frame per 1–2 seconds
- [ ] Rename/popup effects and audit events visible
- [ ] Approval before Submit visible in continuous recording
- [ ] Receipt marked MOCK
- [ ] No actual Aadhaar, phone, bank numbers, production OTP or credentials on screen
- [ ] Captions legible, audio understandable, final length 2–3 minutes
