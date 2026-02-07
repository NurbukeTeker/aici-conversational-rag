"""Definition-only question routing (keyword-based, no LLM).
When True, the agent uses doc-only prompt (no session JSON/summary) to avoid
distracting the LLM with drawing context for purely regulatory definition questions.
"""
from __future__ import annotations

# Phrases that indicate a definition-only / doc-only question (normalized lowercase)
_DEFINITION_PREFIXES = (
    "what is ",
    "define ",
    "definition of ",
    "meaning of ",
    "what does ",
    "what is considered a ",
    "what is considered an ",
    "how is ",
    "how are ",
)
# "what does X mean" — check for "mean" as intent
_DEFINITION_PATTERNS = (" mean", " defined", " definition")

# If any of these appear, do NOT treat as definition-only (drawing/geometry intent)
# Note: "elevation" omitted so "Define principal elevation" is doc_only (regulatory term)
_DRAWING_INTENT_KEYWORDS = frozenset({
    "property", "plot", "boundary", "front", "fronts",
    "distance", "angle", "coordinates", "door", "window", "wall", "layer",
    "json", "drawing", "comply", "allowed", "extension",
})


def _normalize(text: str) -> str:
    """Normalize for matching: strip and lowercase."""
    return (text or "").strip().lower()


def is_definition_only_question(question: str) -> bool:
    """
    Return True if the question is purely a regulatory definition request
    (e.g. "What is a highway?", "Define principal elevation") and should
    use the doc-only prompt without session JSON/summary.

    Must NOT trigger when the question implies drawing/geometry intent
    (e.g. "Does this property front a highway?", "What is a highway in my drawing?").
    """
    if not question or not isinstance(question, str):
        return False
    normalized = _normalize(question)
    if not normalized:
        return False

    # Exclude if any drawing/geometry intent keyword is present
    for keyword in _DRAWING_INTENT_KEYWORDS:
        if keyword in normalized:
            return False

    # Check definition-style phrasing
    for prefix in _DEFINITION_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for pattern in _DEFINITION_PATTERNS:
        if pattern in normalized:
            return True
    return False
