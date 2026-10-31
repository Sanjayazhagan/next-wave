"""Baseline: a plain browser-use agent on the same portal, with the same model and profile.

    uv run --with browser-use python -m modules.bench.baseline_browser_use \
        --profile fixtures/profiles/a.bench.json --url <portal login URL> --runs 5

A person must supervise every run: watch the browser, type any OTP or CAPTCHA, and
answer "did it reach the review page with the right values?" at the end. The task
tells the agent to stop at the review page and never submit; the supervisor stops
it if it tries. Writes rows in bench.py's CSV format with config "baseline".

API checked 31 Oct 2026 (docs.browser-use.com): Agent(task, llm), ChatOpenAI with
base_url/api_key for OpenAI-compatible endpoints; run() returns AgentHistoryList.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from common.config import env

from .bench import Row, write_csv
from .policy import BenchProfile

TASK = """You are helping a student fill a scholarship application on {url}.
Use only these details: {details}.
Log in with portal user id {user}. If an OTP or CAPTCHA appears, wait: a person will type it.
Fill the application form with the details. Upload these files where asked: {docs}.
STOP when you reach the review/preview page. NEVER click Submit, Final Submit, Pay or e-Sign."""


async def one(profile: BenchProfile, url: str, timeout_s: float):
    from browser_use import Agent, ChatOpenAI

    llm = ChatOpenAI(model=env("LLM_MODEL"), base_url=env("LLM_BASE_URL"),
                     api_key=env("LLM_API_KEY"))
    task = TASK.format(url=url, details=", ".join(f"{k}: {v}" for k, v in profile.answers.items()),
                       user=profile.portal_user_id or "(ask the supervisor)", docs=", ".join(profile.documents) or "none")
    agent = Agent(task=task, llm=llm)
    return await asyncio.wait_for(agent.run(), timeout=timeout_s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--portal", default="portal")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args()
    profile = BenchProfile.model_validate_json(a.profile.read_text())
    rows = []
    for i in range(min(a.runs, 10)):
        row = Row(config="baseline", run_idx=i, seed=i)
        t0 = time.monotonic()
        try:
            history = asyncio.run(one(profile, a.url, a.timeout))
            row.llm_calls = history.number_of_steps()
        except Exception as exc:
            row.error = f"{type(exc).__name__}: {exc}"[:200]
        elapsed = round(time.monotonic() - t0, 1)
        verdict = input(f"run {i}: did it reach the review page with every value correct? [y/n] ").strip().lower()
        row.success = verdict == "y" and not row.error
        wait = input("seconds you spent typing OTP/CAPTCHA (0 if none): ").strip() or "0"
        row.human_wait_s = float(wait)
        row.seconds_to_review = round(elapsed - row.human_wait_s, 1) if row.success else None
        rows.append(row)
    print(f"wrote {write_csv(rows, a.portal)}")


if __name__ == "__main__":
    main()
