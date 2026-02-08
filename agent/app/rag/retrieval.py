"""Single retrieval module: retrieve(question) + postprocess(chunks)."""
from __future__ import annotations

import logging
from typing import Any

from langchain_chroma import Chroma

from ..config import get_settings
from .retrieval_postprocess import postprocess

logger = logging.getLogger(__name__)

_vectorstore = None


def get_vectorstore() -> Chroma:
    """Get or create LangChain Chroma vectorstore using shared Chroma client."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore
    from ..chroma_client import get_chroma_client
    settings = get_settings()
    client = get_chroma_client()
    _vectorstore = Chroma(
        client=client,
        collection_name=settings.chroma_collection_name,
    )
    logger.info("LangChain Chroma using shared client, collection '%s'", settings.chroma_collection_name)
    return _vectorstore


def retrieve(
    query: str,
    top_k: int | None = None,
    max_distance: float | None = None,
) -> list[dict]:
    """
    Retrieve documents via LangChain Chroma and postprocess.
    Returns list of chunk dicts: {id, source, page, section, text, distance}.
    """
    settings = get_settings()
    k = top_k if top_k is not None else settings.retrieval_top_k
    max_d = max_distance if max_distance is not None else settings.retrieval_max_distance
    vs = get_vectorstore()
    docs = vs.similarity_search_with_score(query, k=k)
    chunks: list[dict[str, Any]] = []
    for doc, score in docs:
        meta = doc.metadata or {}
        chunk_id = meta.get("chunk_id", meta.get("id", str(getattr(doc, "id", "unknown"))))
        source = meta.get("source", "unknown")
        page = meta.get("page")
        section = meta.get("section")
        text = getattr(doc, "page_content", "")
        distance = score if isinstance(score, (int, float)) else None
        chunks.append({
            "id": chunk_id,
            "source": source,
            "page": str(page) if page is not None else None,
            "section": section,
            "text": text,
            "distance": distance,
        })
    postprocessed = postprocess(chunks, max_distance=max_d)
    logger.info(
        "Retrieval: collection=%s, requested_k=%s, raw_chunks=%s, after_postprocess=%s",
        settings.chroma_collection_name,
        k,
        len(chunks),
        len(postprocessed),
    )
    return postprocessed
