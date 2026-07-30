"""Local evaluation contracts and deterministic metrics."""

from job_scout.evals.deterministic import (
    LocalEvaluationDataset,
    LocalEvaluationReport,
    evaluate_dataset,
)

__all__ = [
    "LocalEvaluationDataset",
    "LocalEvaluationReport",
    "evaluate_dataset",
]
