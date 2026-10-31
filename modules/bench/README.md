# Benchmark harness (M7)

Runs the real agent end to end and records how often it reaches a correct review
page, how long it takes, and how often it repairs itself. **Every run stops at the
review page; nothing is ever submitted** (keep `ALLOW_REAL_SUBMIT=false` on core).

## 1. Profile (git-ignored)

`fixtures/profiles/<name>.bench.json` describes a real person, so it never goes in git:

```json
{
  "language": "en",
  "answers": {"state": "Tamil Nadu", "course": "B.E. first year", "annual_income": "240000", "community": "bc"},
  "documents": ["fixtures/docs/a_marksheet.jpg", "fixtures/docs/a_income.jpg"],
  "scheme_id": "aicte-pragati-degree",
  "portal_user_id": "<their portal login id>",
  "expected": {"full_name": "S Satyajit", "annual_income": "240000"}
}
```

`expected` lists the fields the review page must show, with their values.

## 2. Run our agent

```bash
# .env: AGENT_URL (core API), API_TOKEN (its X-API-Key)
uv run python -m modules.bench.bench --profile fixtures/profiles/a.bench.json --portal nsp --runs 10 --configs ours
```

The harness answers the agent's questions from the profile, uploads the documents,
picks the scheme and stops at the approval prompt. When the agent needs a person
(OTP, CAPTCHA, handover), it prints the prompt and waits: answer it through the
normal channel (Telegram bot or web app). That waiting time is recorded in
`human_wait_s` and left out of `seconds_to_review`.

Run it twice in a row: the first run explores and saves a skill, later runs replay
it (`mode` and `skill_version` columns show which).

It waits 20 to 40 seconds between runs, runs at most 10 per config, and stops
after 3 server errors in a row. Output: `results/<timestamp>_<portal>.csv`.

Not yet measurable, pending core changes (CONFIRM WITH CORE TEAMMATE):
- `llm_calls`, `tokens`, `est_cost_usd`: core doesn't expose its LLM usage.
- `ours-chaos`: needs core to expose the browser session id (or an inject endpoint)
  so the harness can send `modules/chaos/chaos.js` to `POST /session/{id}/inject`.

## 3. Baseline (supervised)

```bash
uv run --with browser-use python -m modules.bench.baseline_browser_use \
  --profile fixtures/profiles/a.bench.json --url <portal URL> --runs 5
```

Plain browser-use with the same model (`LLM_MODEL` on `LLM_BASE_URL`) and the same
details. **A person must watch every baseline run**, type any OTP or CAPTCHA, stop
it if it goes for a submit button, and answer y/n at the end.

## 4. Report

```bash
uv run python -m modules.bench.report results/2026*.csv
```

Writes `results/summary.md` (per config: success rate, median and min-max seconds,
repairs) and `results/chart.png` (success rate and median time, two panels).

Commit CSVs from real runs only. `stub_server.py` is a **test-only** fake used by
the harness's own tests; its CSVs are marked `stub=True` and `report.py` refuses them.
