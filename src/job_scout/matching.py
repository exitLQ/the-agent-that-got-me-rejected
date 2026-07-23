"""Shared text normalization for deterministic matching and evidence."""

from __future__ import annotations

import re
import unicodedata

_SPECIAL_TERMS = {
    ".net": " dotnet ",
    "c#": " csharp ",
    "c++": " cplusplus ",
    "node.js": " nodejs ",
    "scikit-learn": " scikitlearn ",
}


def normalize_match_text(value: str) -> str:
    """Normalize prose while preserving common technical terms."""
    text = value.casefold()
    for source, replacement in _SPECIAL_TERMS.items():
        text = text.replace(source, replacement)
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def phrase_present(phrase: str, text: str) -> bool:
    """Whether a phrase occurs on normalized word boundaries."""
    normalized = normalize_match_text(phrase)
    if not normalized:
        return False
    return bool(re.search(rf"(?:^| ){re.escape(normalized)}(?: |$)", text))
