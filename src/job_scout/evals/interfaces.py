"""Opt-in evaluation interfaces with a deny-by-default external boundary.

Only local JSON adapters ship with the application. Future Opik, judge, or
review-queue integrations can implement these protocols, but the orchestrator
checks their declared boundary before calling either side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from job_scout.evals.deterministic import (
    LocalEvaluationDataset,
    LocalEvaluationReport,
    evaluate_dataset,
)


class EvaluationInterfaceError(RuntimeError):
    """Raised before an unconfirmed external evaluation interface is called."""


class EvaluationDatasetSource(Protocol):
    """Load typed evaluation cases from one declared trust boundary."""

    @property
    def name(self) -> str: ...

    @property
    def is_external(self) -> bool: ...

    def load(self) -> LocalEvaluationDataset: ...


class EvaluationReportSink(Protocol):
    """Publish only a privacy-minimized deterministic evaluation report."""

    @property
    def name(self) -> str: ...

    @property
    def is_external(self) -> bool: ...

    def publish(self, report: LocalEvaluationReport) -> PublishReceipt: ...


class PublishReceipt(BaseModel):
    """Non-sensitive proof that a report reached the selected destination."""

    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1, max_length=300)
    external: bool
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_cases: int = Field(ge=0)
    tailoring_cases: int = Field(ge=0)


@dataclass(frozen=True)
class EvaluationRun:
    """The local report and its non-sensitive publication receipt."""

    report: LocalEvaluationReport
    receipt: PublishReceipt


@dataclass(frozen=True)
class LocalJsonDatasetSource:
    """Read a versioned evaluation dataset from the local filesystem."""

    path: Path

    @property
    def name(self) -> str:
        return "local-json"

    @property
    def is_external(self) -> bool:
        return False

    def load(self) -> LocalEvaluationDataset:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return LocalEvaluationDataset.model_validate(raw)


@dataclass(frozen=True)
class LocalJsonReportSink:
    """Atomically write the minimized report to the local filesystem."""

    path: Path

    @property
    def name(self) -> str:
        return "local-json"

    @property
    def is_external(self) -> bool:
        return False

    def publish(self, report: LocalEvaluationReport) -> PublishReceipt:
        payload = json.dumps(
            report.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text(payload, encoding="utf-8")
            temporary_path.replace(self.path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return PublishReceipt(
            destination=self.name,
            external=False,
            dataset_sha256=report.dataset_sha256,
            profile_cases=report.summary.profile_cases,
            tailoring_cases=report.summary.tailoring_cases,
        )


def _external_interfaces(
    source: EvaluationDatasetSource,
    sink: EvaluationReportSink,
) -> list[str]:
    interfaces = []
    if source.is_external:
        interfaces.append(f"dataset source {source.name!r}")
    if sink.is_external:
        interfaces.append(f"report sink {sink.name!r}")
    return interfaces


def run_evaluation(
    source: EvaluationDatasetSource,
    sink: EvaluationReportSink,
    *,
    confirm_external: bool = False,
) -> EvaluationRun:
    """Evaluate and publish after checking all boundaries before any I/O."""
    external = _external_interfaces(source, sink)
    if external and not confirm_external:
        joined = ", ".join(external)
        raise EvaluationInterfaceError(
            f"External evaluation access requires explicit confirmation: {joined}"
        )
    if (
        isinstance(source, LocalJsonDatasetSource)
        and isinstance(sink, LocalJsonReportSink)
        and source.path.resolve() == sink.path.resolve()
    ):
        raise EvaluationInterfaceError(
            "The evaluation output must not overwrite its input dataset."
        )

    dataset = source.load()
    report = evaluate_dataset(dataset)
    receipt = sink.publish(report)
    if receipt.dataset_sha256 != report.dataset_sha256:
        raise EvaluationInterfaceError(
            "The evaluation destination returned a receipt for another dataset."
        )
    if receipt.external != sink.is_external or receipt.destination != sink.name:
        raise EvaluationInterfaceError(
            "The evaluation destination returned inconsistent boundary metadata."
        )
    return EvaluationRun(report=report, receipt=receipt)
