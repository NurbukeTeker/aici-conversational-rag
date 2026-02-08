"""Postprocess only (no LangChain). Used by retrieval.py and tests."""
from __future__ import annotations

_DISTANCE_NONE = float("inf")
MAX_CHUNKS_PER_PAGE = 2


def _chunk_distance(chunk: dict) -> float:
    d = chunk.get("distance")
    if d is None:
        return _DISTANCE_NONE
    try:
        return float(d)
    except (TypeError, ValueError):
        return _DISTANCE_NONE


def _source_page_key(chunk: dict) -> tuple[str, str | None]:
    return (chunk.get("source") or "unknown", chunk.get("page"))


def postprocess(
    chunks: list[dict],
    max_distance: float | None = None,
    max_per_page: int = MAX_CHUNKS_PER_PAGE,
) -> list[dict]:
    """
    Filter by optional distance threshold, keep up to max_per_page chunks per (source, page)
    (best by distance), then sort by distance ascending (most relevant first).
    """
    if not chunks:
        return []
    if max_distance is not None:
        try:
            max_d = float(max_distance)
        except (TypeError, ValueError):
            max_d = None
        if max_d is not None:
            chunks = [c for c in chunks if _chunk_distance(c) <= max_d]
    by_key: dict[tuple[str, str | None], list[dict]] = {}
    for c in chunks:
        key = _source_page_key(c)
        if key not in by_key:
            by_key[key] = []
        lst = by_key[key]
        lst.append(c)
        lst.sort(key=_chunk_distance)
        if len(lst) > max_per_page:
            lst.pop()
    deduped = [c for lst in by_key.values() for c in lst]
    deduped.sort(key=_chunk_distance)
    return deduped
