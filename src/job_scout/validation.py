"""Deterministic grounding checks for generated application material.

The validator uses normalized string similarity and exact corpus lookups. It
does not call a model, repair output, or hide flags. The same inputs and
thresholds always produce the same report.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from job_scout.config import get_settings
from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import FabricationReport, FlaggedClaim, TailoringPack

_MIN_FACTUAL_SENTENCE_WORDS = 6
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")
_FIRST_PERSON = re.compile(
    r"\b(?:i|i'm|i've|my|me|ich|mein(?:e|er|em|en|es)?|mir|mich)\b",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(?:dear|hello|hi|to whom|sehr geehrte|guten tag|hallo)\b",
    re.IGNORECASE,
)
_SIGN_OFF = re.compile(
    r"^(?:sincerely|regards|best regards|kind regards|yours faithfully|"
    r"mit freundlichen grüßen|freundliche grüße|beste grüße)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Case-fold, remove punctuation, and collapse whitespace."""
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", text.casefold())).strip()


def _ratio(left: str, right: str) -> float:
    """Return normalized deterministic string similarity in the range 0..1."""
    return SequenceMatcher(
        None,
        _normalize(left),
        _normalize(right),
        autojunk=False,
    ).ratio()


def _best_ratio(text: str, references: list[str]) -> float:
    return max((_ratio(text, reference) for reference in references), default=0.0)


def _bullet_ratio(text: str, references: list[str]) -> float:
    """Support one source or an assembled claim backed by up to three sources."""
    candidates = [*references]
    if len(references) > 1:
        candidates.append(" ".join(references))
    return _best_ratio(text, candidates)


def _skill_ratio(skill: str, source: str) -> float:
    """Treat a complete normalized skill phrase inside its source as exact support."""
    normalized_skill = _normalize(skill)
    normalized_source = _normalize(source)
    if normalized_skill and re.search(
        rf"(?<!\w){re.escape(normalized_skill)}(?!\w)",
        normalized_source,
    ):
        return 1.0
    return _ratio(skill, source)


def _context_ratio(claim: str, references: list[str]) -> float:
    """Accept exact normalized phrases, otherwise use best string similarity."""
    normalized_claim = _normalize(claim)
    if normalized_claim and any(
        re.search(rf"(?<!\w){re.escape(normalized_claim)}(?!\w)", _normalize(reference))
        for reference in references
    ):
        return 1.0
    return _best_ratio(claim, references)


def _split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip()
    ]


def _looks_factual(sentence: str) -> bool:
    """Identify only sentences with mechanically checkable factual markers."""
    if len(sentence.split()) < _MIN_FACTUAL_SENTENCE_WORDS:
        return False
    if re.search(r"\d", sentence):
        return True
    return bool(
        re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", sentence[1:])
        or re.search(r"\b[A-Z]{2,}\b", sentence)
    )


def _flag(
    *,
    claim_type: str,
    where: str,
    text: str,
    reason: str,
    corpus_refs: list[str] | None = None,
    ratio: float = 0.0,
) -> FlaggedClaim:
    return FlaggedClaim(
        claim_type=claim_type,
        where=where,
        text=text,
        reason=reason,
        corpus_refs=corpus_refs or [],
        best_match_ratio=round(ratio, 3),
    )


def validate_pack(
    pack: TailoringPack,
    corpus: tuple[CorpusItem, ...] | list[CorpusItem],
    *,
    job_context: list[str] | None = None,
) -> FabricationReport:
    """Check every source-linked or factual claim without using an LLM."""
    settings = get_settings()
    thresholds = {
        "bullet": settings.fab_bullet_ratio,
        "skill": settings.fab_skill_ratio,
        "letter": settings.fab_letter_ratio,
    }
    corpus_by_id = {item.item_id: item for item in corpus}
    corpus_text = [item.text for item in corpus]
    flagged: list[FlaggedClaim] = []
    claims_checked = 0

    for index, bullet in enumerate(pack.tailored_bullets, start=1):
        claims_checked += 1
        missing = [ref for ref in bullet.corpus_refs if ref not in corpus_by_id]
        if missing:
            flagged.append(
                _flag(
                    claim_type="cv_bullet",
                    where=f"cv_bullet:{index}",
                    text=bullet.text,
                    reason=f"corpus references do not resolve: {', '.join(missing)}",
                    corpus_refs=bullet.corpus_refs,
                )
            )
            continue
        sources = [corpus_by_id[ref].text for ref in bullet.corpus_refs]
        similarity = _bullet_ratio(bullet.text, sources)
        if similarity < thresholds["bullet"]:
            flagged.append(
                _flag(
                    claim_type="cv_bullet",
                    where=f"cv_bullet:{index}",
                    text=bullet.text,
                    reason=(
                        "rewrite drifted too far from its cited corpus "
                        f"(ratio {similarity:.2f} < {thresholds['bullet']:.2f})"
                    ),
                    corpus_refs=bullet.corpus_refs,
                    ratio=similarity,
                )
            )

    for index, skill in enumerate(pack.selected_skills, start=1):
        claims_checked += 1
        item = corpus_by_id.get(skill.corpus_ref)
        if item is None:
            flagged.append(
                _flag(
                    claim_type="skill",
                    where=f"skill:{index}",
                    text=skill.name,
                    reason=f"corpus reference does not resolve: {skill.corpus_ref}",
                    corpus_refs=[skill.corpus_ref],
                )
            )
            continue
        similarity = _skill_ratio(skill.name, item.text)
        if similarity < thresholds["skill"]:
            flagged.append(
                _flag(
                    claim_type="skill",
                    where=f"skill:{index}",
                    text=skill.name,
                    reason=(
                        "skill is not supported by its cited corpus item "
                        f"(ratio {similarity:.2f} < {thresholds['skill']:.2f})"
                    ),
                    corpus_refs=[skill.corpus_ref],
                    ratio=similarity,
                )
            )

    job_references = list(job_context or [])
    for index, requirement in enumerate(pack.addressed_requirements, start=1):
        claims_checked += 1
        similarity = _context_ratio(requirement, job_references)
        if similarity < thresholds["letter"]:
            flagged.append(
                _flag(
                    claim_type="job_requirement",
                    where=f"job_requirement:{index}",
                    text=requirement,
                    reason=(
                        "addressed requirement is not traceable to the selected job "
                        f"(best match {similarity:.2f} < {thresholds['letter']:.2f})"
                    ),
                    ratio=similarity,
                )
            )

    letter_references = [*corpus_text, *(job_context or [])]
    for index, sentence in enumerate(_split_sentences(pack.cover_letter), start=1):
        if (
            _GREETING.search(sentence)
            or _SIGN_OFF.search(sentence)
            or not _looks_factual(sentence)
        ):
            continue
        claims_checked += 1
        candidate_claim = bool(_FIRST_PERSON.search(sentence))
        references = corpus_text if candidate_claim else letter_references
        similarity = _best_ratio(sentence, references)
        if similarity < thresholds["letter"]:
            scope = "candidate corpus" if candidate_claim else "corpus or job"
            flagged.append(
                _flag(
                    claim_type="cover_letter",
                    where=f"cover_letter:sentence:{index}",
                    text=sentence,
                    reason=(
                        f"factual claim is not traceable to the {scope} context "
                        f"(best match {similarity:.2f} < {thresholds['letter']:.2f})"
                    ),
                    ratio=similarity,
                )
            )

    return FabricationReport(
        flags=len(flagged),
        claims_checked=claims_checked,
        flagged=flagged,
        thresholds=thresholds,
    )
