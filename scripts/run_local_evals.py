"""Run the versioned, offline deterministic evaluation suite.

Usage:
    uv run python scripts/run_local_evals.py data/evaluation/local_fixture.json
    uv run python scripts/run_local_evals.py INPUT.json --output REPORT.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from job_scout.evals import (
    LocalJsonDatasetSource,
    LocalJsonReportSink,
    run_evaluation,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "reports" / "local_evaluation.json"


def run(input_path: Path, output_path: Path) -> dict:
    """Validate, evaluate, and write one privacy-minimized stable report."""
    evaluation = run_evaluation(
        LocalJsonDatasetSource(input_path),
        LocalJsonReportSink(output_path),
    )
    return evaluation.report.model_dump(mode="json")


def print_summary(payload: dict) -> None:
    summary = payload["summary"]
    print("Local deterministic evaluation")
    print(f"Dataset: {payload['dataset_sha256']}")
    print(
        "Profile field accuracy: "
        f"{summary['matched_profile_fields']}/{summary['total_profile_fields']} "
        f"({summary['profile_field_accuracy']})"
    )
    print(
        "Fabrication rate: "
        f"{summary['fabrication_flags']}/{summary['claims_checked']} "
        f"({summary['fabrication_rate']})"
    )
    print(
        "Citation resolution: "
        f"{summary['citations_resolved']}/{summary['citations_total']} "
        f"({summary['citation_resolution_rate']})"
    )
    print(
        "Cover-letter length compliance: "
        f"{summary['cover_letters_within_limit']}/{summary['tailoring_cases']} "
        f"({summary['cover_letter_compliance_rate']})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local deterministic profile and tailoring evaluation",
    )
    parser.add_argument("input", type=Path, help="versioned local evaluation JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"report path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    payload = run(args.input, args.output)
    print_summary(payload)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
