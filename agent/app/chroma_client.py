"""Shared ChromaDB client so ingestion and retrieval use the same settings (avoids 'instance already exists with different settings')."""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import get_settings

logger = logging.getLogger(__name__)

_chroma_client = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Single Chroma PersistentClient with fixed settings. Used by VectorStoreService and rag.retrieval."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_directory)
    persist_dir.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
        ),
    )
    logger.info(f"Chroma client initialized at {persist_dir}")
    return _chroma_client
