"""Graph-node boundary tests for deterministic tailoring validation."""

from __future__ import annotations

from langgraph.runtime import Runtime

from job_scout.corpus import CorpusItem
from job_scout.graph.nodes.validate_tailoring import validate_tailoring
from job_scout.graph.schemas import JobPosting, RankedJob, TailoringPack
from job_scout.graph.state import AgentContext


def _pack() -> TailoringPack:
    return TailoringPack(
        selected_job_id="job-1",
        cover_letter=(
            "I am applying because this role matches my interest in reliable "
            "data systems and thoughtful engineering."
        ),
        addressed_requirements=["Python", "Reliable systems"],
        tailored_bullets=[
            {
                "text": "Built reliable Python pipelines for analytics workloads.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "The statement is directly supported by the source.",
            }
        ],
        selected_skills=[
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        honesty_note="The CV does not contain evidence for every requested tool.",
    )


def _runtime() -> Runtime[AgentContext]:
    return Runtime(
        context=AgentContext(
            candidate_corpus=(
                CorpusItem(
                    item_id="cv-experience-001",
                    text="Built reliable Python pipelines for analytics workloads.",
                    kind="experience",
                ),
                CorpusItem(
                    item_id="cv-skill-001",
                    text="Python",
                    kind="skill",
                ),
            )
        )
    )


def test_node_skips_validation_when_generation_failed():
    result = validate_tailoring({"tailoring": None}, _runtime())

    assert result == {"fabrication_report": None}


def test_node_attaches_report_without_copying_corpus_text():
    job = RankedJob(
        job=JobPosting(
            job_id="job-1",
            title="Data Engineer",
            company="Example GmbH",
            location="Vienna",
            description="Build reliable systems with Python and data services.",
            tags=["Python"],
            source="cache",
        ),
        fit_score=80,
        fit_explanation="Good match.",
    )

    result = validate_tailoring(
        {
            "tailoring": _pack(),
            "selected_job_id": "job-1",
            "ranked_jobs": [job],
        },
        _runtime(),
    )

    report = result["fabrication_report"]
    assert report.flags == 0
    assert report.claims_checked == 4
    assert "analytics workloads" not in report.model_dump_json()
