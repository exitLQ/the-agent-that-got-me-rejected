"""Validation and deterministic fallbacks for job-search queries."""

from __future__ import annotations

import re

from job_scout.graph.schemas import Profile
from job_scout.matching import normalize_match_text

MAX_QUERY_WORDS = 8
MAX_QUERY_LENGTH = 100

_ADJACENT_ROLES: dict[str, tuple[str, ...]] = {
    "backend engineer": ("software engineer", "platform engineer"),
    "data analyst": ("analytics engineer", "business intelligence analyst"),
    "data engineer": ("analytics engineer", "platform data engineer"),
    "data scientist": ("machine learning engineer", "data analyst"),
    "frontend engineer": ("web developer", "full stack engineer"),
    "full stack engineer": ("software engineer", "backend engineer"),
    "machine learning engineer": ("data scientist", "ai engineer"),
    "ml engineer": ("machine learning engineer", "data scientist"),
    "product manager": ("technical product manager", "product owner"),
    "software engineer": ("backend engineer", "platform engineer"),
}
_SENIORITY_WORDS = {
    "associate",
    "entry",
    "junior",
    "lead",
    "mid",
    "principal",
    "senior",
    "staff",
}


def query_key(query: str) -> str:
    """Canonical key used for duplicate detection."""
    return normalize_match_text(query)


def sanitize_query(value: str | None) -> str | None:
    """Accept a short role/skill query and reject prose or unsafe output."""
    if not value:
        return None
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    cleaned = first_line.replace("```", "").strip(" `\"'")
    cleaned = re.sub(
        r"^(?:new |broader |alternative )?(?:search )?query\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.rstrip(".").strip(" `\"'")
    words = cleaned.split()
    normalized = query_key(cleaned)
    if (
        not cleaned
        or len(cleaned) > MAX_QUERY_LENGTH
        or len(words) > MAX_QUERY_WORDS
        or "://" in cleaned
        or any(word.upper() in {"AND", "NOT", "OR"} for word in words)
        or normalized.startswith(("here is ", "i suggest ", "try searching "))
    ):
        return None
    if not normalized:
        return None
    return cleaned


def _role_without_seniority(role: str) -> str:
    tokens = [
        token
        for token in normalize_match_text(role).split()
        if token not in _SENIORITY_WORDS
    ]
    return " ".join(tokens)


def fallback_query(
    profile: Profile,
    history: list[str],
    *,
    attempt: int,
) -> str:
    """Choose a short deterministic query not already present in history."""
    roles = [
        role
        for role in (_role_without_seniority(item) for item in profile.primary_roles)
        if role
    ]
    skills = [skill.strip() for skill in profile.skills if skill.strip()]
    primary = roles[0] if roles else ""
    adjacent = list(_ADJACENT_ROLES.get(primary, ()))

    if attempt <= 0:
        candidates = [
            " ".join([primary, *skills[:2]]),
            primary,
            " ".join(skills[:3]),
        ]
    elif attempt == 1:
        candidates = [
            " ".join([role, *skills[:1]]) for role in adjacent
        ] + roles[1:] + [primary]
    else:
        candidates = adjacent[1:] + roles[1:] + adjacent[:1] + [
            primary,
            " ".join(skills[:2]),
        ]

    candidates.extend(["technology specialist", "software professional"])
    seen = {query_key(item) for item in history}
    for candidate in candidates:
        cleaned = sanitize_query(candidate)
        if cleaned and query_key(cleaned) not in seen:
            return cleaned
    return f"technology role attempt {attempt + 1}"
