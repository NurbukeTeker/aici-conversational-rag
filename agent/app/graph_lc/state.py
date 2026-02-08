"""Graph state for LangGraph hybrid RAG workflow."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from ..models import SessionSummary

QueryMode = Literal["doc_only", "json_only", "hybrid"]


class GraphState(TypedDict, total=False):
    """State for the LangGraph answer workflow."""

    question: str
    session_objects: list[dict[str, Any]]
    session_summary: SessionSummary | None
    doc_only: bool
    query_mode: QueryMode
    retrieved_docs: list[dict]
    answer_text: str
    guard_result: dict | None
    # Injected at runtime by graph_builder; used by retrieve_node (_settings), validate/summarize/finalize (_reasoning_service)
    _settings: Any
    _reasoning_service: Any
