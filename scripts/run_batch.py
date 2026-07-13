"""Phase 1 baseline batch runner.

Runs the agent over the fixture CVs across a committed matrix of location
variations plus deliberately hard cases (~50 runs), tags every trace
``baseline-batch``, and writes reports/baseline.json + a printed markdown table.

This produces Post 1's payoff numbers and Phase 2's raw material. It does NOT
fix anything it surfaces — failures and weaknesses are documented in
reports/phase1_findings.md, then fixed only in Phase 3.

Usage:
    uv run python scripts/run_batch.py            # prints projected cost, then stops
    uv run python scripts/run_batch.py --yes      # actually runs
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from job_scout.config import get_settings
from job_scout.runner import run_once
from job_scout.tools.cv_reader import extract_cv_text

ROOT = Path(__file__).resolve().parent.parent
CV_DIR = ROOT / "data" / "fixture_cvs"
REPORT_PATH = ROOT / "reports" / "baseline.json"

# Rough per-run cost for the projection prompt (a run makes ~4-8 gpt-4o-mini calls).
COST_PER_RUN_ESTIMATE = 0.006

# 3 English CVs x location variations across >= 4 countries + remote.
ENGLISH_CVS = ["junior_ds_us.pdf", "senior_mle_eu.pdf", "career_changer_in.pdf"]
VARIATIONS: list[tuple[str | None, str]] = [
    (None, "no location hint"),
    ("New York, USA", "us"),
    ("San Francisco, USA", "us"),
    ("London, UK", "uk"),
    ("Manchester, UK", "uk"),
    ("Berlin, Germany", "de"),
    ("Munich, Germany", "de"),
    ("Bengaluru, India", "in"),
    ("Mumbai, India", "in"),
    ("Sydney, Australia", "au"),
    ("São Paulo, Brazil", "br"),
    ("Remote", "remote-only"),
    ("Remote worldwide", "remote-only"),
    ("Toronto, Canada", "ca"),
    ("Singapore", "sg"),
]


@dataclass
class Case:
    case_id: str
    cv_file: str
    location_hint: str | None
    note: str
    hard: bool = False


def build_matrix() -> list[Case]:
    cases: list[Case] = []
    for cv in ENGLISH_CVS:
        stem = cv.replace(".pdf", "")
        for hint, note in VARIATIONS:
            cases.append(Case(f"{stem}|{note}", cv, hint, note))

    # 5 deliberately hard cases.
    cases += [
        Case("hard|non_english_de", "german_pm_de.pdf", None, "non-English (German) CV", hard=True),
        Case("hard|junior_low_exp", "junior_ds_us.pdf", "Remote", "junior, minimal experience, remote", hard=True),
        Case("hard|career_changer", "career_changer_in.pdf", "Bengaluru, India", "career changer, thin experience", hard=True),
        Case("hard|niche_skills", "senior_mle_eu.pdf", None, "very niche senior skill set", hard=True),
        Case("hard|unmappable_loc", "career_changer_in.pdf", "Atlantis", "location maps to no Adzuna country", hard=True),
    ]
    return cases


def _cv_text(case: Case) -> str:
    text = extract_cv_text(CV_DIR / case.cv_file)
    if case.location_hint:
        text += f"\n\nPreferred location: {case.location_hint}"
    return text


def _fit_distribution(scores: list[int]) -> dict[str, int]:
    buckets = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
    for s in scores:
        if s < 20:
            buckets["0-19"] += 1
        elif s < 40:
            buckets["20-39"] += 1
        elif s < 60:
            buckets["40-59"] += 1
        elif s < 80:
            buckets["60-79"] += 1
        else:
            buckets["80-100"] += 1
    return buckets


def run(cases: list[Case]) -> dict:
    rows = []
    all_scores: list[int] = []
    latencies: list[float] = []
    costs: list[float] = []

    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.case_id} ({case.note})…", flush=True)
        result = run_once(
            _cv_text(case),
            cv_path=str(CV_DIR / case.cv_file),
            thread_id=str(uuid4()),
            tags=["phase-1", "baseline-batch"],
        )
        scores = [r.fit_score for r in result.ranked_jobs]
        all_scores += scores
        latencies.append(result.latency_s)
        costs.append(result.cost_usd)
        rows.append(
            {
                "case_id": case.case_id,
                "cv_file": case.cv_file,
                "location_hint": case.location_hint,
                "note": case.note,
                "hard": case.hard,
                "failed": result.failed,
                "error_message": result.error_message,
                "n_jobs_fetched": result.n_jobs_fetched,
                "n_jobs_ranked": result.n_jobs_ranked,
                "reformulation_count": result.reformulation_count,
                "jobs_sources": result.jobs_sources,
                "fit_scores": scores,
                "errors": result.errors,
                "cost_usd": result.cost_usd,
                "latency_s": result.latency_s,
            }
        )

    failures = [r for r in rows if r["failed"]]
    empty = [r for r in rows if not r["failed"] and r["n_jobs_ranked"] == 0]
    reformulated = [r for r in rows if r["reformulation_count"] > 0]

    def _pctl(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        k = min(len(s) - 1, int(round(p * (len(s) - 1))))
        return round(s[k], 3)

    summary = {
        "runs": len(rows),
        "failures": len(failures),
        "empty_result_runs": len(empty),
        "reformulation_triggered": len(reformulated),
        "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else 0,
        "latency_median_s": round(statistics.median(latencies), 2) if latencies else 0,
        "latency_p95_s": _pctl(latencies, 0.95),
        "cost_mean_usd": round(statistics.mean(costs), 5) if costs else 0,
        "cost_total_usd": round(sum(costs), 4),
        "fit_score_distribution": _fit_distribution(all_scores),
        "fit_score_mean": round(statistics.mean(all_scores), 1) if all_scores else 0,
    }
    return {"summary": summary, "runs": rows}


def print_table(summary: dict) -> None:
    print("\n## Baseline batch summary\n")
    print("| metric | value |")
    print("|---|---|")
    for key in [
        "runs",
        "failures",
        "empty_result_runs",
        "reformulation_triggered",
        "latency_mean_s",
        "latency_median_s",
        "latency_p95_s",
        "cost_mean_usd",
        "cost_total_usd",
        "fit_score_mean",
    ]:
        print(f"| {key} | {summary[key]} |")
    print("\n**Fit-score distribution:**")
    for bucket, count in summary["fit_score_distribution"].items():
        print(f"- {bucket}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 baseline batch runner")
    parser.add_argument("--yes", action="store_true", help="run without the cost confirmation prompt")
    args = parser.parse_args()

    cases = build_matrix()
    projected = len(cases) * COST_PER_RUN_ESTIMATE
    settings = get_settings()
    print(f"Model: {settings.scout_model}")
    print(f"Planned runs: {len(cases)}")
    print(f"Projected cost: ~${projected:.2f} (at ~${COST_PER_RUN_ESTIMATE:.3f}/run)")

    if not args.yes:
        print("\nRe-run with --yes to execute.")
        sys.exit(0)

    report = run(cases)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print_table(report["summary"])
    print(f"\nWrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
