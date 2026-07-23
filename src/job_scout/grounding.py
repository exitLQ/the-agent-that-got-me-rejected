"""Ground displayed skill matches and gaps in profile and job evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from job_scout.graph.schemas import JobPosting, Profile, SkillEvidence
from job_scout.matching import normalize_match_text, phrase_present

_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "C#": ("c#", "csharp"),
    "C++": ("c++", "cplusplus"),
    "Docker": ("docker",),
    "GCP": ("gcp", "google cloud", "google cloud platform"),
    "Git": ("git", "github", "gitlab"),
    "Java": ("java",),
    "JavaScript": ("javascript", "js"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Machine Learning": ("machine learning", "ml"),
    ".NET": (".net", "dotnet"),
    "Node.js": ("node.js", "nodejs"),
    "Pandas": ("pandas",),
    "PostgreSQL": ("postgresql", "postgres"),
    "PyTorch": ("pytorch",),
    "Python": ("python",),
    "React": ("react", "reactjs", "react.js"),
    "Rust": ("rust",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "Spark": ("apache spark", "spark"),
    "SQL": ("sql",),
    "TensorFlow": ("tensorflow",),
    "Terraform": ("terraform",),
    "TypeScript": ("typescript", "ts"),
}
_REQUIREMENT_CUES = {
    "experience",
    "experienced",
    "familiar",
    "knowledge",
    "must",
    "need",
    "needed",
    "proficient",
    "required",
    "requirement",
    "requirements",
    "skill",
    "skills",
}
_NON_REQUIREMENT_PHRASES = {
    "bonus",
    "nice to have",
    "no experience",
    "not need",
    "not required",
    "optional",
}
_NEGATED_REQUIREMENT_PATTERNS = (
    r"(?:^| )no (?:[a-z0-9]+ ){0,3}experience(?: |$)",
    r"(?:^| )not (?:[a-z0-9]+ ){0,3}need(?:ed)?(?: |$)",
    r"(?:^| )not (?:[a-z0-9]+ ){0,3}required(?: |$)",
)


@dataclass(frozen=True)
class _Evidence:
    text: str
    requirement: bool


def _normalized_aliases(aliases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_match_text(alias) for alias in aliases)


def _canonical_group(skill: str) -> tuple[str, tuple[str, ...]]:
    """Resolve a profile or model skill to a known group, or keep it literal."""
    normalized = normalize_match_text(skill)
    for canonical, aliases in _SKILL_ALIASES.items():
        if normalized in _normalized_aliases(aliases):
            return canonical, aliases
    return skill.strip(), (skill,)


def _sentence_candidates(description: str) -> list[str]:
    """Split prose into compact evidence candidates."""
    return [
        " ".join(part.split())
        for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", description)
        if part.strip()
    ]


def _has_alias(text: str, aliases: tuple[str, ...]) -> bool:
    normalized = normalize_match_text(text)
    return any(phrase_present(alias, normalized) for alias in aliases)


def _find_evidence(job: JobPosting, aliases: tuple[str, ...]) -> _Evidence | None:
    """Find the strongest short job-side evidence for one skill."""
    if _has_alias(job.title, aliases):
        return _Evidence(text=f"title: {job.title}", requirement=True)
    for tag in job.tags:
        if _has_alias(tag, aliases):
            return _Evidence(text=f"tag: {tag}", requirement=True)
    for sentence in _sentence_candidates(job.description):
        if not _has_alias(sentence, aliases):
            continue
        normalized = set(normalize_match_text(sentence).split())
        excerpt = sentence if len(sentence) <= 180 else f"{sentence[:177].rstrip()}..."
        return _Evidence(
            text=f"description: {excerpt}",
            requirement=bool(normalized & _REQUIREMENT_CUES),
        )
    return None


def _negated_or_optional(evidence: str) -> bool:
    normalized = normalize_match_text(evidence)
    return any(
        phrase_present(phrase, normalized) for phrase in _NON_REQUIREMENT_PHRASES
    ) or any(re.search(pattern, normalized) for pattern in _NEGATED_REQUIREMENT_PATTERNS)


def _profile_groups(profile: Profile) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Return unique canonical groups keyed by normalized canonical name."""
    groups: dict[str, tuple[str, tuple[str, ...]]] = {}
    for skill in profile.skills:
        canonical, aliases = _canonical_group(skill)
        key = normalize_match_text(canonical)
        if key:
            groups.setdefault(key, (skill.strip(), aliases))
    return groups


def profile_skill_group_count(profile: Profile) -> int:
    """Count unique profile skills after alias canonicalization."""
    return len(_profile_groups(profile))


def ground_skill_evidence(
    profile: Profile,
    job: JobPosting,
) -> tuple[list[SkillEvidence], list[SkillEvidence]]:
    """Return evidence-backed profile matches and job-only skill gaps."""
    profile_groups = _profile_groups(profile)
    matched: list[SkillEvidence] = []
    for _key, (profile_skill, aliases) in profile_groups.items():
        evidence = _find_evidence(job, aliases)
        if evidence:
            matched.append(
                SkillEvidence(
                    skill=profile_skill,
                    profile_evidence=f"profile.skills: {profile_skill}",
                    job_evidence=evidence.text,
                )
            )

    gaps: list[SkillEvidence] = []
    for canonical, aliases in _SKILL_ALIASES.items():
        key = normalize_match_text(canonical)
        if key in profile_groups:
            continue
        evidence = _find_evidence(job, aliases)
        if evidence and evidence.requirement and not _negated_or_optional(evidence.text):
            gaps.append(
                SkillEvidence(
                    skill=canonical,
                    profile_evidence="not present in profile.skills",
                    job_evidence=evidence.text,
                )
            )

    return matched, gaps
