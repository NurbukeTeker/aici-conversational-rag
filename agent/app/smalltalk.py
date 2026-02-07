"""Lightweight small-talk detection for greetings and pleasantries.
When detected, the agent returns a short friendly response without running RAG or returning evidence.
"""
from __future__ import annotations

# Domain keywords: if any appear in the message, do NOT treat as small talk
DOMAIN_KEYWORDS = (
    "property", "highway", "plot", "boundary", "elevation",
    "planning", "development", "wall", "window", "door",
    "json", "layer",
)

SMALLTALK_MAX_WORDS = 4

# Normalized greeting/pleasantry phrases (lowercase, no punctuation in set)
# Message is matched after: strip, lower, and optional trailing punctuation stripped
SMALLTALK_PHRASES = frozenset({
    "hi", "hello", "hey", "hey there", "hi there",
    "good morning", "good afternoon", "good evening",
    "morning", "afternoon", "evening", "good day",
    "thanks", "thank you", "thx", "thanks!", "thank you!",
    "how are you", "how are you doing", "how's it going",
    "how do you do", "greetings", "howdy",
})

SMALLTALK_RESPONSE = (
    "Hi! I can help with planning regulations and your current drawing JSON. "
    "What would you like to check?"
)


def _normalize(message: str) -> str:
    """Normalize for comparison: strip and lowercase."""
    return message.strip().lower()


def _strip_trailing_punctuation(text: str) -> str:
    """Remove trailing punctuation for phrase matching."""
    while text and text[-1] in ".,!?;:":
        text = text[:-1]
    return text.strip()


def is_smalltalk(message: str) -> bool:
    """
    Return True only if the message is short greeting/pleasantry with no domain keywords.
    - Message must be short (<= SMALLTALK_MAX_WORDS).
    - Message must not contain any domain keyword (e.g. property, highway, plot).
    - Normalized message must match a known small-talk phrase.
    """
    if not message or not isinstance(message, str):
        return False
    normalized = _normalize(message)
    if not normalized:
        return False
    words = normalized.split()
    if len(words) > SMALLTALK_MAX_WORDS:
        return False
    for keyword in DOMAIN_KEYWORDS:
        if keyword in normalized:
            return False
    phrase = _strip_trailing_punctuation(normalized)
    return phrase in SMALLTALK_PHRASES
