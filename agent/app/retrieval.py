"""Retrieval postprocessing: keep top N per (source, page), distance threshold, sort by distance."""
from __future__ import annotations

# Sentinel for missing distance (sort last / treat as low relevance)
_DISTANCE_NONE = float("inf")

# Max chunks to keep per (source, page) before sorting and returning
MAX_CHUNKS_PER_PAGE = 2


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
    """Key for grouping: (source, page)."""
    return (chunk.get("source") or "unknown", chunk.get("page"))


def postprocess_retrieved_chunks(
    chunks: list[dict],
    max_distance: float | None = None,
    max_per_page: int = MAX_CHUNKS_PER_PAGE,
) -> list[dict]:
    """
    Filter by optional distance threshold, keep up to max_per_page chunks per (source, page)
    (best by distance), then sort by distance ascending (most relevant first).

    - max_distance: if set, drop chunks with distance > max_distance (Chroma L2; lower = better).
    - max_per_page: max chunks to keep per (source, page); default 2 to reduce loss from same page.
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

    # 2. Per (source, page), keep up to max_per_page best (smallest distance)
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

    # 3. Flatten and sort by distance ascending (most relevant first)
    deduped = [c for lst in by_key.values() for c in lst]
    deduped.sort(key=_chunk_distance)
    return deduped
