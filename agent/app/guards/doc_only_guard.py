"""DOC_ONLY guard: only answer definition-style questions when the asked term appears in retrieved context.
Prevents the LLM from inventing definitions (e.g. 'side elevation') when the PDF doesn't define them.
"""
from __future__ import annotations

import re


def _normalize(t: str) -> str:
    return (t or "").strip().lower()


# Quote characters that may wrap the term (straight and smart/curly)
_QUOTE_CHARS = "'\"\u2018\u2019\u201c\u201d"


def _normalize_term_for_match(term: str) -> str:
    """Strip quotes and normalize so term matches chunk text (e.g. principal elevation matches principal-elevation)."""
    if not term:
        return ""
    t = (term or "").strip().lower()
    while t and t[0] in _QUOTE_CHARS:
        t = t[1:].strip()
    while t and t[-1] in _QUOTE_CHARS:
        t = t[:-1].strip()
    # Treat hyphens as space so "principal elevation" matches "principal-elevation" in docs
    return t.replace("-", " ")


def extract_definition_term(question: str) -> str | None:
    """
    Extract the term the user is asking to have defined (e.g. "side elevation", "curtilage").
    Returns None if no clear definition-style term is found (then we don't apply the guard).
    """
    if not question or not isinstance(question, str):
        return None
    q = question.strip()
    if not q:
        return None
    normalized = _normalize(q)

    # "what is meant by 'X'" or "what is meant by \"X\"" (straight and smart/curly quotes)
    m = re.search(r"what\s+is\s+meant\s+by\s+[\"'\u201c\u2018]([^\"'\u201d\u2019?]+)[\"'\u201d\u2019]?\s*\??\s*$", normalized, re.I)
    if m:
        term = m.group(1).strip()
        if term and len(term) < 80:
            return _normalize_term_for_match(term)

    # "what is meant by X" (no quotes) — take next phrase up to ? or ,
    m = re.search(r"what\s+is\s+meant\s+by\s+([^?,]+?)(?:\s*[?,]|\s*$)", normalized, re.I)
    if m and m.group(1):
        term = m.group(1).strip()
        if term and len(term) < 80:
            return _normalize_term_for_match(term)

    # "what is the definition of a highway?" / "what is the definition of X?" → extract X (e.g. "highway")
    m = re.search(
        r"what\s+is\s+the\s+(?:definition|meaning)\s+of\s+(?:a|an|the)\s+([^?]+?)\s*\??\s*$",
        normalized,
        re.I,
    )
    if m and m.group(1):
        term = m.group(1).strip()
        if term and len(term) < 80:
            return _normalize_term_for_match(term)
    m = re.search(
        r"what\s+is\s+the\s+(?:definition|meaning)\s+of\s+([^?]+?)\s*\??\s*$",
        normalized,
        re.I,
    )
    if m and m.group(1):
        term = m.group(1).strip()
        if term and len(term) < 80:
            return _normalize_term_for_match(term)

    # "what is a X?", "what is the X?" (generic — avoid capturing "definition of a X")
    m = re.search(r"what\s+is\s+(?:a|an|the)\s+([^?]+?)\s*\??\s*$", normalized, re.I)
    if m and m.group(1):
        term = m.group(1).strip()
        if term and len(term) < 80:
            return _normalize_term_for_match(term)

    # "define X", "definition of X", "meaning of X"
    for prefix in ("define ", "definition of ", "meaning of "):
        if normalized.startswith(prefix):
            rest = normalized[len(prefix) :].strip()
            if not rest:
                continue
            term = re.split(r"\s*[?,]\s*", rest)[0].strip()
            if term and len(term) < 80:
                return _normalize_term_for_match(term)

    return None


def term_appears_in_chunks(term: str, chunks: list[dict]) -> bool:
    """True if the term (normalized) appears in at least one chunk's text.
    Term is normalized (strip quotes, hyphens as space) so smart quotes and hyphenation don't block matches.
    """
    if not term or not chunks:
        return False
    needle = _normalize_term_for_match(term)
    if not needle:
        return False
    for c in chunks:
        text = c.get("text") or c.get("page_content") or ""
        # Normalize chunk text the same way (hyphen as space) so "principal-elevation" matches "principal elevation"
        chunk_norm = _normalize(text).replace("-", " ")
        if needle in chunk_norm:
            return True
    return False


def should_use_retrieved_for_doc_only(question: str, retrieved_chunks: list[dict]) -> bool:
    """
    One rule: for DOC_ONLY, only use retrieved chunks (and call the LLM) if the asked-for
    term appears in the context. Otherwise return "not found" to avoid invented definitions.
    If no definition term can be extracted, we allow the LLM (don't block vague questions).
    """
    if not retrieved_chunks:
        return False
    term = extract_definition_term(question)
    if term is None:
        return True  # no clear term → allow LLM
    return term_appears_in_chunks(term, retrieved_chunks)
