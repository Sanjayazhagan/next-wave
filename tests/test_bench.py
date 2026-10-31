"""The harness against the TEST-ONLY stub server. These numbers are never reported."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from modules.bench import bench, report
from modules.bench.client import AgentClient
from modules.bench.policy import BenchProfile
from modules.bench.stub_server import app


@pytest.fixture
def client():
    return AgentClient("http://stub", "k", http=TestClient(app))


def test_bench_reaches_review_against_stub_and_never_approves(client, tmp_path, monkeypatch):
    doc = tmp_path / "marksheet.jpg"
    doc.write_bytes(b"\xff\xd8\xff fake")
    profile = BenchProfile(answers={"state": "Tamil Nadu"}, documents=[str(doc)], expected={"state": "Tamil Nadu"})
    row = bench.run_once(client, profile, "ours", 0, 7, timeout_s=30, poll_s=0)
    assert row.success and row.seconds_to_review is not None and row.stub
    assert row.repairs == 1 and row.portal_id == "stub-portal"

    monkeypatch.setattr(bench, "RESULTS", tmp_path)
    path = bench.write_csv([row], "stub")
    with pytest.raises(report.StubResults):
        report.load([path])


def test_wrong_value_is_not_success(client):
    profile = BenchProfile(answers={"state": "Kerala"}, expected={"state": "Tamil Nadu"})
    row = bench.run_once(client, profile, "ours", 0, 7, timeout_s=30, poll_s=0)
    assert not row.success and "differ" in row.error


def test_chaos_config_is_reported_as_unsupported(client):
    row = bench.run_once(client, BenchProfile(answers={}), "ours-chaos", 0, 7)
    assert not row.success and "TODO" in row.error


def test_report_summary_and_chart(tmp_path):
    rows = [bench.Row(config="ours", run_idx=i, seed=i, success=i != 2, seconds_to_review=40.0 + i,
                      repairs=i % 2) for i in range(4)]
    path = tmp_path / "real.csv"
    import csv
    from dataclasses import asdict
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    s = report.summarise(report.load([path]))
    assert s["ours"]["success_rate"] == 75.0 and s["ours"]["median_s"] == 41.0
    report.write_markdown(s, tmp_path / "summary.md")
    report.write_chart(s, tmp_path / "chart.png")
    assert (tmp_path / "chart.png").stat().st_size > 1000 and "75.0%" in (tmp_path / "summary.md").read_text()
