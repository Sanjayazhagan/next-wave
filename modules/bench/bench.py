"""Benchmark the real agent end to end. It always stops at the review page and never submits.

    uv run python -m modules.bench.bench --profile fixtures/profiles/a.bench.json --runs 10 --configs ours

Per run it records: config, run_idx, seed, success, seconds_to_review (excluding
time spent waiting for a human), human_wait_s, repairs, strikes, handovers, mode,
skill_version, outcome, error, stub. Output: results/<timestamp>_<portal>.csv.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from common.textnorm import norm_text

from .client import AgentClient
from .policy import BenchProfile, Policy

RESULTS = Path(__file__).resolve().parents[2] / "results"
MAX_RUNS = 10
MAX_SERVER_ERRORS = 3
POLL_S = 1.0


@dataclass
class Row:
    config: str
    run_idx: int
    seed: int
    success: bool = False
    seconds_to_review: float | None = None
    human_wait_s: float = 0.0
    # Core doesn't expose its LLM usage yet. CONFIRM WITH CORE TEAMMATE: add counts to GET /session.
    llm_calls: int | None = None
    tokens: int | None = None
    est_cost_usd: float | None = None
    repairs: int = 0
    strikes: int = 0
    handovers: int = 0
    mode: str | None = None
    skill_version: int | None = None
    outcome: str | None = None
    portal_id: str | None = None
    error: str = ""
    stub: bool = False


def fields_match(view: dict, expected: dict[str, str]) -> bool:
    """Every expected field was filled on the form, with the value from the profile.

    `filled` maps field -> {label, source_document, confidence}; the typed value is the
    profile's value for that field (GET /session shows it, masked only for ID numbers).
    """
    filled, profile = view.get("filled") or {}, view.get("profile") or {}
    return bool(expected) and all(
        k in filled and norm_text(str((profile.get(k) or {}).get("value", ""))) == norm_text(v)
        for k, v in expected.items())


def run_once(client: AgentClient, profile: BenchProfile, config: str, run_idx: int, seed: int,
             timeout_s: float = 900, poll_s: float = POLL_S, say=print) -> Row:
    row = Row(config=config, run_idx=run_idx, seed=seed)
    if config.endswith("-chaos"):
        # Chaos needs the browser worker's session id, which core doesn't expose.
        # CONFIRM WITH CORE TEAMMATE: expose it in GET /session, or add POST /session/{id}/inject.
        row.error = "chaos configs need core to expose the browser session (TODO)"
        return row
    policy = Policy(profile)
    sid = client.start()
    t0 = time.monotonic()
    answered: tuple | None = None
    while time.monotonic() - t0 < timeout_s:
        view = client.view(sid)
        row.stub = row.stub or client.stub
        row.mode, row.skill_version = view.get("mode"), view.get("skill_version")
        row.outcome, row.portal_id = view.get("outcome"), view.get("portal_id")
        kind, prompt = view.get("pending_kind"), view.get("prompt") or {}
        if view.get("status") not in ("running", "paused"):
            row.error = row.error or f"session ended: {view.get('status')} {row.outcome or ''}".strip()
            break
        if kind == "approval":
            row.seconds_to_review = round(time.monotonic() - t0 - row.human_wait_s, 1)
            row.success = fields_match(view, profile.expected)
            if not row.success:
                row.error = "review page reached but filled fields differ from the profile"
            break   # never approve: the benchmark stops at the review page
        key = (kind, prompt.get("text"), len(policy.uploaded))
        if view.get("status") == "paused" and kind and key != answered:
            ans = policy.answer(kind, prompt)
            if ans is None:
                row.handovers += kind == "handover"
                say(f"[run {run_idx}] needs a human: {kind}: {prompt.get('text', '')[:120]}")
                w0 = time.monotonic()
                while (v := client.view(sid)).get("pending_kind") == kind and time.monotonic() - t0 < timeout_s:
                    time.sleep(poll_s)
                row.human_wait_s += round(time.monotonic() - w0, 1)
                continue
            if ans.upload:
                client.upload(sid, ans.upload)
            else:
                client.reply(sid, text=ans.text, button=ans.button)
            answered = key
        time.sleep(poll_s)
    else:
        row.error = f"timed out after {timeout_s:.0f}s"
    events = client.audit(sid)
    row.repairs = sum(1 for e in events if e.get("step") == "self_repair")
    row.strikes = sum(1 for e in events if "failed" in (e.get("message") or "") and e.get("message", "").startswith("Try "))
    return row


def write_csv(rows: list[Row], portal: str) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d_%H%M%S}_{portal}.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    return path


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--portal", default="portal", help="label for the CSV file name")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--configs", default="ours")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--gap", type=float, nargs=2, default=(20, 40), help="seconds between runs (min max)")
    a = ap.parse_args()
    profile = BenchProfile.model_validate_json(a.profile.read_text())
    client = AgentClient(os.getenv("AGENT_URL", "http://localhost:8000"), os.getenv("API_TOKEN", ""))
    rng = random.Random(a.seed)
    rows, server_errors = [], 0
    for config in a.configs.split(","):
        for i in range(min(a.runs, MAX_RUNS)):
            try:
                row = run_once(client, profile, config, i, a.seed + i)
                server_errors = 0
            except httpx.HTTPError as exc:
                row = Row(config=config, run_idx=i, seed=a.seed + i, error=f"{type(exc).__name__}: {exc}"[:200])
                server_errors += 1
            rows.append(row)
            print(f"{config} #{i}: success={row.success} t={row.seconds_to_review} repairs={row.repairs} {row.error}")
            if server_errors >= MAX_SERVER_ERRORS:
                print("3 server errors in a row; stopping")
                break
            time.sleep(rng.uniform(*a.gap))
    print(f"wrote {write_csv(rows, a.portal)}")


if __name__ == "__main__":
    main()
