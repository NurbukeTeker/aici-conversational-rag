"""LangChain Chroma vectorstore + retriever for hybrid RAG."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

from .config import get_settings
from .retrieval import postprocess_retrieved_chunks

logger = logging.getLogger(__name__)

_retriever = None
_vectorstore = None


def _doc_to_chunk(doc: Any) -> dict:
    """Convert LangChain Document to chunk dict for Evidence compatibility."""
    meta = doc.metadata or {}
    text = getattr(doc, "page_content", str(doc))
    return {
        "id": meta.get("chunk_id", meta.get("id", doc.id if hasattr(doc, "id") else "unknown")),
        "source": meta.get("source", "unknown"),
        "page": meta.get("page"),
        "section": meta.get("section"),
        "text": text,
        "distance": getattr(doc, "distance", meta.get("distance")),
    }


def get_vectorstore() -> Chroma:
    """Get or create LangChain Chroma vectorstore using shared Chroma client (same settings as ingestion)."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore
    from .chroma_client import get_chroma_client
    settings = get_settings()
    client = get_chroma_client()
    _vectorstore = Chroma(
        client=client,
        collection_name=settings.chroma_collection_name,
    )
    logger.info(f"LangChain Chroma using shared client, collection '{settings.chroma_collection_name}'")
    return _vectorstore


def get_retriever(top_k: int | None = None):
    """Get retriever for hybrid RAG. Uses same Chroma collection as ingestion."""
    global _retriever
    settings = get_settings()
    k = top_k if top_k is not None else settings.retrieval_top_k
    vs = get_vectorstore()
    _retriever = vs.as_retriever(search_kwargs={"k": k})
    return _retriever


def retrieve(
    query: str,
    top_k: int | None = None,
    max_distance: float | None = None,
) -> list[dict]:
    """
    Retrieve documents via LangChain retriever and postprocess.
    Returns list of chunk dicts: {id, source, page, section, text, distance}.
    """
    settings = get_settings()
    k = top_k if top_k is not None else settings.retrieval_top_k
    max_d = max_distance if max_distance is not None else settings.retrieval_max_distance

    vs = get_vectorstore()
    # LangChain Chroma similarity_search_with_score returns (doc, score)
    # Chroma uses L2 distance - lower is better; langchain may expose as score (higher=better) or distance
    docs = vs.similarity_search_with_score(query, k=k)

    chunks = []
    for doc, score in docs:
        # Chroma returns L2 distance as score when using similarity_search_with_score
        # In Chroma, "score" is typically the distance (lower = better)
        meta = doc.metadata or {}
        chunk_id = meta.get("chunk_id", meta.get("id", str(getattr(doc, "id", "unknown"))))
        source = meta.get("source", "unknown")
        page = meta.get("page")
        section = meta.get("section")
        text = getattr(doc, "page_content", "")
        # Chroma L2: lower score = more similar
        distance = score if isinstance(score, (int, float)) else None
        chunks.append({
            "id": chunk_id,
            "source": source,
            "page": str(page) if page is not None else None,
            "section": section,
            "text": text,
            "distance": distance,
        })

    postprocessed = postprocess_retrieved_chunks(chunks, max_distance=max_d)
    logger.info(
        "Retrieval: collection=%s, requested_k=%s, raw_chunks=%s, after_postprocess=%s",
        settings.chroma_collection_name,
        k,
        len(chunks),
        len(postprocessed),
    )
    return postprocessed
