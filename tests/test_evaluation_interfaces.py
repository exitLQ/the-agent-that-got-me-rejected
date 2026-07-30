"""Deny-by-default boundaries for optional evaluation adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from job_scout.evals import (
    EvaluationInterfaceError,
    LocalEvaluationDataset,
    LocalJsonDatasetSource,
    LocalJsonReportSink,
    PublishReceipt,
    run_evaluation,
)

FIXTURE = Path("data/evaluation/local_fixture.json")


@dataclass
class FakeSource:
    dataset: LocalEvaluationDataset
    is_external: bool
    name: str = "fake-source"
    calls: int = 0

    def load(self) -> LocalEvaluationDataset:
        self.calls += 1
        return self.dataset


@dataclass
class FakeSink:
    is_external: bool
    name: str = "fake-sink"
    calls: int = 0
    received_text: str = ""
    wrong_digest: bool = False
    wrong_boundary: bool = False

    def publish(self, report) -> PublishReceipt:
        self.calls += 1
        self.received_text = report.model_dump_json()
        digest = "0" * 64 if self.wrong_digest else report.dataset_sha256
        return PublishReceipt(
            destination="another-sink" if self.wrong_boundary else self.name,
            external=not self.is_external if self.wrong_boundary else self.is_external,
            dataset_sha256=digest,
            profile_cases=report.summary.profile_cases,
            tailoring_cases=report.summary.tailoring_cases,
        )


def _dataset() -> LocalEvaluationDataset:
    return LocalEvaluationDataset.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("source_external", "sink_external"),
    [(True, False), (False, True), (True, True)],
)
def test_external_interfaces_are_blocked_before_any_adapter_call(
    source_external,
    sink_external,
):
    source = FakeSource(_dataset(), is_external=source_external)
    sink = FakeSink(is_external=sink_external)

    with pytest.raises(EvaluationInterfaceError, match="explicit confirmation"):
        run_evaluation(source, sink)

    assert source.calls == 0
    assert sink.calls == 0


def test_explicit_confirmation_allows_declared_external_adapters():
    source = FakeSource(_dataset(), is_external=True)
    sink = FakeSink(is_external=True)

    evaluation = run_evaluation(source, sink, confirm_external=True)

    assert source.calls == 1
    assert sink.calls == 1
    assert evaluation.receipt.external is True
    assert evaluation.receipt.dataset_sha256 == evaluation.report.dataset_sha256
    assert "Test Candidate" not in sink.received_text
    assert "Built Python data services" not in sink.received_text


def test_local_json_adapters_need_no_external_confirmation(tmp_path):
    output = tmp_path / "report.json"

    evaluation = run_evaluation(
        LocalJsonDatasetSource(FIXTURE),
        LocalJsonReportSink(output),
    )

    assert output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    assert evaluation.receipt.destination == "local-json"
    assert evaluation.receipt.external is False


def test_local_interfaces_refuse_the_same_input_and_output_path():
    with pytest.raises(EvaluationInterfaceError, match="must not overwrite"):
        run_evaluation(
            LocalJsonDatasetSource(FIXTURE),
            LocalJsonReportSink(FIXTURE),
        )


def test_mismatched_publication_receipt_is_rejected():
    source = FakeSource(_dataset(), is_external=False)
    sink = FakeSink(is_external=False, wrong_digest=True)

    with pytest.raises(EvaluationInterfaceError, match="another dataset"):
        run_evaluation(source, sink)


def test_inconsistent_sink_boundary_receipt_is_rejected():
    source = FakeSource(_dataset(), is_external=False)
    sink = FakeSink(is_external=False, wrong_boundary=True)

    with pytest.raises(EvaluationInterfaceError, match="boundary metadata"):
        run_evaluation(source, sink)
