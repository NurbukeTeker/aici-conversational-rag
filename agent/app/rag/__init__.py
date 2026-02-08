"""RAG module: prompts, chains, retrieval, and answer orchestration."""

# No langchain dependency: safe for tests that only need prompts or postprocess
from .prompts import (
    SYSTEM_PROMPT,
    format_chunk_for_prompt,
    format_chunk,
    format_retrieved_chunks,
    build_user_prompt,
    build_user_prompt_doc_only,
)
from .retrieval_postprocess import postprocess

__all__ = [
    "SYSTEM_PROMPT",
    "HYBRID_PROMPT",
    "DOC_ONLY_PROMPT",
    "format_chunk_for_prompt",
    "format_chunk",
    "format_retrieved_chunks",
    "build_user_prompt",
    "build_user_prompt_doc_only",
    "build_chains",
    "invoke_doc_only",
    "invoke_hybrid",
    "astream_doc_only",
    "astream_hybrid",
    "DOC_ONLY_EMPTY_MESSAGE",
    "retrieve",
    "postprocess",
    "run_answer",
    "stream_answer_ndjson",
]


def __getattr__(name: str):
    """Lazy load LangChain-dependent modules so tests can import prompts/postprocess only."""
    if name in ("HYBRID_PROMPT", "DOC_ONLY_PROMPT", "build_chains", "invoke_doc_only", "invoke_hybrid",
                "astream_doc_only", "astream_hybrid", "DOC_ONLY_EMPTY_MESSAGE"):
        from . import chains
        return getattr(chains, name)
    if name == "retrieve":
        from . import retrieval
        return getattr(retrieval, name)
    if name in ("run_answer", "stream_answer_ndjson"):
        from . import orchestrator
        return getattr(orchestrator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
