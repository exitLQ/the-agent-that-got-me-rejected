"""Local evaluation contracts and deterministic metrics."""

from job_scout.evals.deterministic import (
    LocalEvaluationDataset,
    LocalEvaluationReport,
    evaluate_dataset,
)
from job_scout.evals.interfaces import (
    EvaluationDatasetSource,
    EvaluationInterfaceError,
    EvaluationReportSink,
    LocalJsonDatasetSource,
    LocalJsonReportSink,
    PublishReceipt,
    run_evaluation,
)

__all__ = [
    "LocalEvaluationDataset",
    "LocalEvaluationReport",
    "EvaluationDatasetSource",
    "EvaluationInterfaceError",
    "EvaluationReportSink",
    "LocalJsonDatasetSource",
    "LocalJsonReportSink",
    "PublishReceipt",
    "evaluate_dataset",
    "run_evaluation",
]
