"""Question routing: DOC_ONLY, JSON_ONLY, HYBRID (keyword-based, no LLM).
Determines which evidence to use and whether to run retrieval.
"""
from __future__ import annotations

from typing import Literal

# Query mode for evidence pipeline
QueryMode = Literal["doc_only", "json_only", "hybrid"]

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
_DEFINITION_PATTERNS = (" mean", " defined", " definition")

# If any of these appear, do NOT treat as definition-only (drawing/geometry intent)
_DRAWING_INTENT_KEYWORDS = frozenset({
    "property", "plot", "boundary", "front", "fronts",
    "distance", "angle", "coordinates", "door", "window", "wall", "layer",
    "json", "drawing", "comply", "allowed", "extension",
})

# Phrases/keywords that indicate JSON-only (counting/listing session objects; no doc lookup)
_JSON_ONLY_PREFIXES = (
    "how many ",
    "list ",
    "list the ",
    "what layers ",
    "which layers ",
    "count ",
    "number of ",
    "what is the width of ",
    "what is the height of ",
    "what is the area of ",
    "what is the name of ",
)
_JSON_ONLY_PATTERNS = (
    " layers ",
    " layer ",
    " objects ",
    " drawing ",
    " in the drawing",
    " in this drawing",
    " present",
    " are there",
)


def _normalize(text: str) -> str:
    """Normalize for matching: strip and lowercase."""
    return (text or "").strip().lower()


def is_definition_only_question(question: str) -> bool:
    """
    Return True if the question is purely a regulatory definition request
    (e.g. "What is a highway?", "Define principal elevation") and should
    use the doc-only prompt without session JSON/summary.
    """
    if not question or not isinstance(question, str):
        return False
    normalized = _normalize(question)
    if not normalized:
        return False
    for keyword in _DRAWING_INTENT_KEYWORDS:
        if keyword in normalized:
            return False
    for prefix in _DEFINITION_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for pattern in _DEFINITION_PATTERNS:
        if pattern in normalized:
            return True
    return False


def is_json_only_question(question: str) -> bool:
    """
    Return True if the question is purely about counting/listing session objects
    (e.g. "How many drawing layers are present?", "List the layers") and does NOT
    need document retrieval. Evidence will be session_objects only.
    """
    if not question or not isinstance(question, str):
        return False
    normalized = _normalize(question)
    if not normalized:
        return False
    # Must not be definition-style (definitions need docs)
    if is_definition_only_question(question):
        return False
    for prefix in _JSON_ONLY_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for pattern in _JSON_ONLY_PATTERNS:
        if pattern in normalized:
            return True
    if "how many " in normalized and ("layer" in normalized or "object" in normalized):
        return True
    if "what layer" in normalized or "which layer" in normalized:
        return True
    # Object property from drawing: "what is the width/height/area of X"
    if "what is the " in normalized and any(
        p in normalized for p in ("width of ", "height of ", "area of ", "name of ")
    ):
        return True
    return False


def get_query_mode(question: str) -> QueryMode:
    """
    Classify question into doc_only, json_only, or hybrid.
    Order: json_only checked after doc_only so "what is a highway?" stays doc_only.
    """
    if not question or not isinstance(question, str):
        return "hybrid"
    if is_definition_only_question(question):
        return "doc_only"
    if is_json_only_question(question):
        return "json_only"
    return "hybrid"
