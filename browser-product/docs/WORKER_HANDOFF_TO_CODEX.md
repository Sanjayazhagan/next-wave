# Codex handoff — adapt, don't replace teammate's agent

Your assigned repository is `Sanjayazhagan/next-wave`, branch
`feat/browser-product` only. The supplied ZIP has **one root folder**:
`browser-product/`. Do not make an orphan branch, force-push, or replace main.

The teammate's `main` is the SOURCE OF TRUTH for the agentic LangGraph, LLM,
conversations and approvals. The Browser Product branch is the tool/execution
service and product frontend, not a competing agent. The browser decides
*whether an action is safe/observed/authorized*, never the user's intent.

## Added here

- `browser/core_compat.py`: live Playwright adapter for core's legacy `/session`
  calls, with operator-controlled portal registry, safe target grounding,
  optional profile ID fill, user challenge pass-through, session-local
  single-use review-bound approval and no invented receipt.
- `server/core_gateway.py`: authenticated `/core-browser/...` reverse proxy to
  the private Playwright worker.
- Integrated mode (`APP_MODE=integrated`) accepts real configured origins,
  refuses synthetic portal endpoints and demands signed identity/encryption.
- `docs/BRIDGE_FIX_HANDOFF_OCT31.md`: integration guidance against the latest main; the previous patch was removed to avoid overwriting new core code.
- Tests: in-memory real Chromium DOM and a localhost HTTP smoke test that can
  run in environments allowing browser navigation.

## Your primary work

1. Review latest main; rebase minimal patch, do not clobber new teammate work.
2. Run main's LangGraph with real LLM and this worker, verify actual decisions.
3. Map real portal login/OTP/CAPTCHA and handle human challenges correctly.
4. Test actual enabled portal with permission and complete at least five
   journeys per portal; record failures/unsupported steps.
5. Update portal-specific receipt extraction/validation, forms, additional
   HTTP methods if permissible, and consent/approval evidence.
6. Deploy with Docker HTTPS on **Mumbai VM**, keep worker internal, test real
   portal reachability **from VM** before committing to a portal.
7. Use production-grade secret management, signed auth, backup/monitoring and
   durable event storage before real citizen data.

Codex may refactor or rewrite the browser module if necessary. It should
minimize edits to his main branch and must preserve the existing LangGraph,
security, verified data provenance, human OTP/CAPTCHA, citizen approval and
noninvented receipts. Latest user chat instructions have priority unless they
would compromise mandatory safety/compliance.
