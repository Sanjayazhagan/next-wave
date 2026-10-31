"""Summarise benchmark CSVs into results/summary.md and results/chart.png.

    uv run python -m modules.bench.report results/2026*.csv

Refuses any CSV produced against the test-only stub server.
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results"

# Reference palette (dataviz skill): series slot 1 on the light chart surface.
SERIES = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#2b2b29"
MUTED = "#6b6a63"
GRID = "#e4e3de"


class StubResults(ValueError):
    pass


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("stub", "").lower() == "true":
                    raise StubResults(f"{p.name} came from the test-only stub server; it must never be reported")
                rows.append(r)
    return rows


def summarise(rows: list[dict]) -> dict[str, dict]:
    by = defaultdict(list)
    for r in rows:
        by[r["config"]].append(r)
    out = {}
    for config, rs in by.items():
        times = [float(r["seconds_to_review"]) for r in rs if r["success"] == "True" and r["seconds_to_review"]]
        repairs = [int(r["repairs"]) for r in rs]
        out[config] = {
            "runs": len(rs),
            "success_rate": round(100 * sum(r["success"] == "True" for r in rs) / len(rs), 1),
            "median_s": round(statistics.median(times), 1) if times else None,
            "min_s": min(times) if times else None, "max_s": max(times) if times else None,
            "mean_repairs": round(statistics.mean(repairs), 2), "max_repairs": max(repairs),
            "human_wait_mean_s": round(statistics.mean(float(r["human_wait_s"] or 0) for r in rs), 1),
        }
    return out


def write_markdown(summary: dict[str, dict], path: Path) -> None:
    lines = ["| Config | Runs | Success | Median s to review (min-max) | Repairs mean (max) | Human wait mean s |",
             "| --- | --- | --- | --- | --- | --- |"]
    for c, s in summary.items():
        t = f"{s['median_s']} ({s['min_s']}-{s['max_s']})" if s["median_s"] is not None else "n/a"
        lines.append(f"| {c} | {s['runs']} | {s['success_rate']}% | {t} | {s['mean_repairs']} ({s['max_repairs']}) | "
                     f"{s['human_wait_mean_s']} |")
    lines.append("\nSeconds exclude time spent waiting for a person (OTP, CAPTCHA, handover). "
                 "Every run stopped at the review page; nothing was submitted.")
    path.write_text("\n".join(lines) + "\n")


def write_chart(summary: dict[str, dict], path: Path) -> None:
    """Two panels, not a dual axis: success rate (%) and median seconds to review."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    configs = list(summary)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), facecolor=SURFACE)
    panels = [("Success rate", "Runs reaching a correct review page (%)", [summary[c]["success_rate"] for c in configs], "%"),
              ("Time to review page", "Median seconds (successful runs)", [summary[c]["median_s"] or 0 for c in configs], " s")]
    for ax, (title, ylabel, values, unit) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        bars = ax.bar(configs, values, width=0.55, color=SERIES, zorder=2)
        ax.set_title(title, color=INK, fontsize=12, loc="left")
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        for b, v in zip(bars, values):
            ax.annotate(f"{v:g}{unit}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", color=INK, fontsize=9)
    if max(summary[c]["success_rate"] for c in configs) > 0:
        axes[0].set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+", type=Path)
    a = ap.parse_args()
    summary = summarise(load(a.csvs))
    RESULTS.mkdir(exist_ok=True)
    write_markdown(summary, RESULTS / "summary.md")
    write_chart(summary, RESULTS / "chart.png")
    print((RESULTS / "summary.md").read_text())


if __name__ == "__main__":
    main()
