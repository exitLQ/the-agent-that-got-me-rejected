"""Runner contract: the search always passes selected_job_id explicitly.

This is the state-reset guarantee from the spec — a run must never route into
stale Phase-2 tailoring state on a reused checkpointer thread.
"""

from __future__ import annotations

from types import SimpleNamespace

import job_scout.runner as runner_mod
from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import (
    FabricationReport,
    JobPosting,
    RankedJob,
    TailoringPack,
)
from job_scout.graph.state import AgentContext
from job_scout.runner import run_once, stream_search, stream_tailoring


class _FakeGraph:
    def __init__(self):
        self.captured_inputs = None

    def stream(self, inputs, config, stream_mode):
        self.captured_inputs = inputs
        return iter([])  # no node updates

    def get_state(self, config):
        return SimpleNamespace(
            values={
                "profile": None,
                "ranked_jobs": [],
                "jobs_sources": ["cache"],
                "query_history": ["data scientist", "data analyst"],
                "ranking_batch_count": 3,
                "ranking_workers": 2,
                "ranking_latency_s": 0.75,
                "ranking_failed_batches": 0,
            }
        )


def _patch(monkeypatch, fake):
    monkeypatch.setattr(runner_mod, "build_graph", lambda: fake)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda g, t: g)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *a, **k: None)


def test_search_passes_profile_and_nulls_selected_job_id(monkeypatch, sample_profile):
    fake = _FakeGraph()
    _patch(monkeypatch, fake)
    monkeypatch.setattr(runner_mod, "extract_profile", lambda *a, **k: sample_profile)

    run_once("cv text here", thread_id="t1", tags=["batch"])

    assert fake.captured_inputs["profile"] is sample_profile
    assert fake.captured_inputs["selected_job_id"] is None
    assert fake.captured_inputs["tailoring"] is None
    assert fake.captured_inputs["fabrication_report"] is None
    assert "cv_text" not in fake.captured_inputs


def test_stream_search_yields_result(monkeypatch, sample_profile):
    fake = _FakeGraph()
    _patch(monkeypatch, fake)

    events = list(
        stream_search(
            sample_profile,
            thread_id="t1",
            tags=["ui"],
            model_name="anthropic:claude-sonnet-4-6",
        )
    )
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert fake.captured_inputs["model"] == "anthropic:claude-sonnet-4-6"
    assert result.model == "anthropic:claude-sonnet-4-6"
    assert result.jobs_sources == ["cache"]
    assert result.query_history == ["data scientist", "data analyst"]
    assert result.ranking_batch_count == 3
    assert result.ranking_workers == 2
    assert result.ranking_latency_s == 0.75
    assert result.failed is False


def _ranked_job() -> RankedJob:
    return RankedJob(
        job=JobPosting(
            job_id="job-1",
            title="Data Scientist",
            company="Example",
            location="Berlin",
            description="Build Python models.",
            source="cache",
        ),
        fit_score=85,
        fit_explanation="Strong match.",
    )


def _tailoring_pack() -> TailoringPack:
    return TailoringPack(
        selected_job_id="job-1",
        cover_letter=(
            "I am applying for this data science role because my Python "
            "experience supports the modelling work described in the posting."
        ),
        addressed_requirements=["Python", "Predictive modelling"],
        tailored_bullets=[
            {
                "text": "Built Python models for production analytics workflows.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "The rewrite stays within the cited experience.",
            }
        ],
        selected_skills=[
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        honesty_note="The CV does not evidence every tool requested by the employer.",
    )


class _FakeTailoringGraph:
    def __init__(self, pack):
        self.pack = pack
        self.report = FabricationReport(
            flags=0,
            claims_checked=2,
            flagged=[],
            thresholds={"bullet": 0.65, "skill": 0.85, "letter": 0.55},
        )
        self.captured_inputs = None
        self.captured_config = None
        self.captured_context = None

    def stream(self, inputs, config, context, stream_mode):
        self.captured_inputs = inputs
        self.captured_config = config
        self.captured_context = context
        return iter(
            [
                {"tailor": {"tailoring": self.pack, "errors": []}},
                {"validate_tailoring": {"fabrication_report": self.report}},
            ]
        )

    def get_state(self, config):
        return SimpleNamespace(
            values={
                "tailoring": self.pack,
                "fabrication_report": self.report,
                "errors": [],
            }
        )


def test_tailoring_runner_passes_explicit_state_and_runtime_only_corpus(
    monkeypatch,
    sample_profile,
):
    pack = _tailoring_pack()
    fake = _FakeTailoringGraph(pack)
    _patch(monkeypatch, fake)
    corpus = [
        CorpusItem(
            item_id="cv-experience-001",
            text="Built Python models for production analytics workflows.",
            kind="experience",
        ),
        CorpusItem(item_id="cv-skill-001", text="Python", kind="skill"),
    ]

    events = list(
        stream_tailoring(
            sample_profile,
            [_ranked_job()],
            corpus,
            selected_job_id="job-1",
            thread_id="t1",
            tags=["ui"],
            model_name="ollama:tailor-test",
        )
    )

    assert events[0] == ("status", "application draft prepared")
    assert events[1] == ("status", "checked 2 claims… 0 require review")
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert result.tailoring == pack
    assert result.fabrication_report == fake.report
    assert result.model == "ollama:tailor-test"
    assert result.failed is False

    assert fake.captured_inputs["profile"] is sample_profile
    assert fake.captured_inputs["ranked_jobs"][0].job.job_id == "job-1"
    assert fake.captured_inputs["selected_job_id"] == "job-1"
    assert fake.captured_inputs["tailoring"] is None
    assert fake.captured_inputs["fabrication_report"] is None
    assert "candidate_corpus" not in fake.captured_inputs
    assert "candidate_corpus" not in fake.captured_config
    assert fake.captured_context == AgentContext(
        candidate_corpus=tuple(corpus),
        tailor_model="ollama:tailor-test",
    )
