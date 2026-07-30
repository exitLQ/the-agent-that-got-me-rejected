"""Deterministic tests for the temporary resume corpus."""

from __future__ import annotations

from job_scout.corpus import build_candidate_corpus
from job_scout.tools.cv_reader import extract_cv_text


def test_corpus_types_fixture_resume_sections():
    text = """
    Jane Example
    jane@example.com | +43 660 123 4567
    Summary
    Data engineer building reliable
    analytics systems.
    Skills
    Python, SQL, Apache Kafka
    Experience
    Data Engineer, Example GmbH (2022-2025)
    - Built streaming pipelines processing 2M events per day.
    - Improved reliability by 30%.
    Education
    M.Sc. Computer Science, Example University (2022).
    """

    corpus = build_candidate_corpus(text)

    assert [item.kind for item in corpus] == [
        "summary",
        "skill",
        "skill",
        "skill",
        "experience",
        "experience",
        "experience",
        "education",
    ]
    assert corpus[0].text == "Data engineer building reliable analytics systems."
    assert [item.text for item in corpus[1:4]] == ["Python", "SQL", "Apache Kafka"]


def test_corpus_ids_are_deterministic_and_addressable():
    text = "Skills\nPython, SQL\nExperience\n- Built an API.\n- Operated it."

    first = build_candidate_corpus(text)
    second = build_candidate_corpus(text)

    assert first == second
    assert [item.item_id for item in first] == [
        "cv-skill-001",
        "cv-skill-002",
        "cv-experience-001",
        "cv-experience-002",
    ]


def test_corpus_removes_preamble_and_contact_channels():
    text = """
    Jane Example
    jane.secret@example.com | +43 (660) 123-4567 | https://portfolio.example
    Summary
    Security engineer.
    Experience
    Contacted customers through support@example.com.
    """

    corpus = build_candidate_corpus(text)
    rendered = " ".join(item.text for item in corpus)

    assert "Jane Example" not in rendered
    assert "jane.secret@example.com" not in rendered
    assert "support@example.com" not in rendered
    assert "+43" not in rendered
    assert "https://" not in rendered
    assert "Security engineer." in rendered


def test_phone_redaction_preserves_year_ranges():
    text = """
    Candidate
    Summary
    Available at +43 660 123 4567.
    Experience
    Data Engineer, Example GmbH (2021-2026)
    """

    rendered = " ".join(item.text for item in build_candidate_corpus(text))

    assert "+43 660 123 4567" not in rendered
    assert "2021-2026" in rendered


def test_headerless_resume_is_redacted_and_retained_as_summary():
    corpus = build_candidate_corpus("Alex Example\nalex@example.com\nBuilt data products.")

    assert [item.kind for item in corpus] == ["summary"]
    assert corpus[0].text == "Built data products."


def test_german_section_names_are_supported():
    text = """
    Person
    Zusammenfassung
    Data Product Manager.
    Kenntnisse
    SQL, Tableau, A/B-Tests
    Berufserfahrung
    - Erstellung von Dashboards.
    Ausbildung
    M.Sc. Wirtschaftsinformatik.
    """

    corpus = build_candidate_corpus(text)

    assert [item.kind for item in corpus] == [
        "summary",
        "skill",
        "skill",
        "skill",
        "experience",
        "education",
    ]


def test_real_fixture_produces_no_contact_data():
    text = extract_cv_text("data/fixture_cvs/career_changer_in.pdf")

    corpus = build_candidate_corpus(text)
    rendered = " ".join(item.text for item in corpus)

    assert corpus
    assert "priya.nair@example.com" not in rendered
    assert any(item.kind == "experience" for item in corpus)
    assert any(item.kind == "skill" and item.text == "basic Python" for item in corpus)
