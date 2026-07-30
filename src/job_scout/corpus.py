"""Build a temporary, addressable corpus from extracted resume text.

The corpus is designed for grounded application tailoring. It deliberately
omits the resume preamble, contact details, and the original unsegmented text.
Callers must keep the returned items in session memory only.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

CorpusKind = Literal["experience", "skill", "education", "summary"]

_SECTION_KIND: dict[str, CorpusKind] = {
    "summary": "summary",
    "professional summary": "summary",
    "profile": "summary",
    "zusammenfassung": "summary",
    "profil": "summary",
    "skills": "skill",
    "technical skills": "skill",
    "competencies": "skill",
    "kenntnisse": "skill",
    "fahigkeiten": "skill",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "employment": "experience",
    "berufserfahrung": "experience",
    "erfahrung": "experience",
    "education": "education",
    "academic background": "education",
    "ausbildung": "education",
    "akademischer werdegang": "education",
}
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_CANDIDATE = re.compile(r"(?<!\w)(?:\+?\d[\d(). /-]{6,}\d)(?!\w)")
_BULLET = re.compile(r"^\s*[-*•●▪◦]\s*")
_SPACE = re.compile(r"\s+")
_SKILL_SEPARATOR = re.compile(r"\s*[,;|]\s*")
_TERMINAL = (".", "!", "?", ":", ";", ")", "]")


class CorpusItem(BaseModel):
    """One typed, addressable, CV-derived fact available to the tailor."""

    item_id: str = Field(pattern=r"^cv-(?:experience|skill|education|summary)-\d{3}$")
    text: str = Field(min_length=2, max_length=1000)
    kind: CorpusKind
    source: Literal["cv"] = "cv"


def _normalized_header(line: str) -> str:
    value = line.strip().casefold().rstrip(":")
    value = (
        value.replace("ä", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ß", "ss")
    )
    return _SPACE.sub(" ", value)


def _sanitize(line: str) -> str:
    """Remove direct contact channels before text can become a corpus item."""
    value = _EMAIL.sub("", line)
    value = _URL.sub("", value)
    value = _PHONE_CANDIDATE.sub(
        lambda match: (
            ""
            if len(re.sub(r"\D", "", match.group())) >= 9
            and (match.group().startswith("+") or bool(re.search(r"[(). /-]", match.group())))
            else match.group()
        ),
        value,
    )
    value = value.replace("  |", " |").replace("|  ", "| ")
    value = value.strip(" \t|,;")
    return _SPACE.sub(" ", value)


def _section_lines(cv_text: str) -> list[tuple[CorpusKind, str, bool]]:
    """Return sanitized physical lines after the first recognized section."""
    output: list[tuple[CorpusKind, str, bool]] = []
    current_kind: CorpusKind | None = None
    found_header = False
    raw_lines = [line.strip() for line in cv_text.replace("\r", "\n").splitlines()]

    for raw_line in raw_lines:
        if not raw_line:
            continue
        section = _SECTION_KIND.get(_normalized_header(raw_line))
        if section:
            current_kind = section
            found_header = True
            continue
        if not found_header:
            continue
        if current_kind is None:
            continue
        sanitized = _sanitize(raw_line)
        if sanitized:
            output.append((current_kind, _BULLET.sub("", sanitized), bool(_BULLET.match(sanitized))))

    if found_header:
        return output

    # Headerless resumes still get a useful, contact-redacted summary corpus.
    return [
        ("summary", sanitized, bool(_BULLET.match(sanitized)))
        for line in raw_lines[1:]
        if (sanitized := _BULLET.sub("", _sanitize(line)))
    ]


def _join_wrapped_lines(
    lines: list[tuple[CorpusKind, str, bool]],
) -> list[tuple[CorpusKind, str]]:
    """Join obvious PDF line wraps without merging separate bullet points."""
    logical: list[tuple[CorpusKind, str, bool]] = []
    for kind, text, is_bullet in lines:
        if (
            logical
            and logical[-1][0] == kind
            and not is_bullet
            and not logical[-1][1].endswith(_TERMINAL)
            and (kind in {"summary", "skill"} or logical[-1][2])
        ):
            previous_kind, previous_text, previous_bullet = logical[-1]
            logical[-1] = (previous_kind, f"{previous_text} {text}", previous_bullet)
        else:
            logical.append((kind, text, is_bullet))
    return [(kind, text) for kind, text, _ in logical]


def _expand_skills(lines: list[tuple[CorpusKind, str]]) -> list[tuple[CorpusKind, str]]:
    """Turn a comma-separated skill section into individually addressable facts."""
    expanded: list[tuple[CorpusKind, str]] = []
    for kind, text in lines:
        if kind != "skill":
            expanded.append((kind, text))
            continue
        skills = [skill.strip().rstrip(".") for skill in _SKILL_SEPARATOR.split(text)]
        expanded.extend((kind, skill) for skill in skills if len(skill) >= 2)
    return expanded


def build_candidate_corpus(cv_text: str) -> list[CorpusItem]:
    """Create deterministic, contact-redacted corpus items from resume text."""
    lines = _expand_skills(_join_wrapped_lines(_section_lines(cv_text)))
    counters: dict[CorpusKind, int] = {
        "experience": 0,
        "skill": 0,
        "education": 0,
        "summary": 0,
    }
    items: list[CorpusItem] = []
    for kind, text in lines:
        normalized = _SPACE.sub(" ", text).strip()
        if len(normalized) < 2:
            continue
        counters[kind] += 1
        items.append(
            CorpusItem(
                item_id=f"cv-{kind}-{counters[kind]:03d}",
                text=normalized[:1000],
                kind=kind,
            )
        )
    return items
