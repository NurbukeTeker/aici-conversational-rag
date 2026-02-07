"""Retrieval postprocessing: dedupe by (source, page) and optional distance threshold."""
from __future__ import annotations

# Sentinel for missing distance (sort last / treat as low relevance)
_DISTANCE_NONE = float("inf")


def _chunk_distance(chunk: dict) -> float:
    """Return numeric distance for ordering; lower is more relevant. Chroma uses L2 distance."""
    d = chunk.get("distance")
    if d is None:
        return _DISTANCE_NONE
    try:
        return float(d)
    except (TypeError, ValueError):
        return _DISTANCE_NONE


def _source_page_key(chunk: dict) -> tuple[str, str | None]:
    """Key for deduplication: (source, page)."""
    return (chunk.get("source") or "unknown", chunk.get("page"))


def postprocess_retrieved_chunks(
    chunks: list[dict],
    max_distance: float | None = None,
) -> list[dict]:
    """
    Filter by optional distance threshold, dedupe by (source, page) keeping best chunk,
    then sort by distance ascending (most relevant first).

    - max_distance: if set, drop chunks with distance > max_distance (Chroma L2; lower = better).
    - Per (source, page), only the chunk with smallest distance is kept.
    - Output order: ascending by distance (stable).
    """
    if not chunks:
        return []

    # 1. Optional filter by distance threshold
    if max_distance is not None:
        try:
            max_d = float(max_distance)
        except (TypeError, ValueError):
            max_d = None
        if max_d is not None:
            chunks = [c for c in chunks if _chunk_distance(c) <= max_d]

    # 2. Dedupe by (source, page), keeping best (smallest distance)
    by_key: dict[tuple[str, str | None], dict] = {}
    for c in chunks:
        key = _source_page_key(c)
        if key not in by_key or _chunk_distance(c) < _chunk_distance(by_key[key]):
            by_key[key] = c
    deduped = list(by_key.values())

    # 3. Sort by distance ascending (most relevant first)
    deduped.sort(key=_chunk_distance)
    return deduped
