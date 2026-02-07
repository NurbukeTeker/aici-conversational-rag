"""LangGraph node functions for hybrid RAG (LangChain-native)."""
from __future__ import annotations

import json
import logging
from typing import Any

from .. import smalltalk
from .. import geometry_guard
from .. import followups
from .. import routing
from .state import GraphState

logger = logging.getLogger(__name__)


def validate_node(state: GraphState) -> dict[str, Any]:
    """Validate session_objects; log warnings."""
    reasoning_service = state.get("_reasoning_service")
    if reasoning_service:
        warnings = reasoning_service.validate_json_schema(state.get("session_objects", []))
        if warnings:
            logger.warning("JSON validation warnings: %s", warnings)
    return {}


def smalltalk_node(state: GraphState) -> dict[str, Any]:
    """If is_smalltalk: set guard_result and answer_text."""
    question = state.get("question", "")
    if smalltalk.is_smalltalk(question):
        logger.info("Small-talk detected, skipping RAG")
        return {"guard_result": {"type": "smalltalk"}}
    return {"guard_result": None}


def geometry_guard_node(state: GraphState) -> dict[str, Any]:
    """If question is about this drawing (not general rule) + spatial + missing geometry: set guard_result."""
    question = state.get("question", "")
    session_objects = state.get("session_objects", [])

    if not geometry_guard.should_trigger_geometry_guard(question):
        return {"guard_result": None}

    required = geometry_guard.required_layers_for_question(question)
    missing = geometry_guard.missing_geometry_layers(session_objects, required)
    if missing:
        logger.info("Geometry guard: missing geometry for %s", missing)
        return {"guard_result": {"type": "missing_geometry", "missing_layers": sorted(missing)}}
    return {"guard_result": None}


def followup_node(state: GraphState) -> dict[str, Any]:
    """If needs-input followup + missing layers: set guard_result."""
    question = state.get("question", "")
    session_objects = state.get("session_objects", [])

    if not followups.is_needs_input_followup(question):
        return {}

    missing_layers = followups.get_missing_geometry_layers(session_objects)
    if missing_layers:
        logger.info("Needs-input follow-up: returning checklist for %s", missing_layers)
        return {"guard_result": {"type": "needs_input", "missing_layers": missing_layers}}
    return {}


def summarize_node(state: GraphState) -> dict[str, Any]:
    """Compute session_summary using ReasoningService."""
    reasoning_service = state.get("_reasoning_service")
    session_objects = state.get("session_objects", [])

    if not reasoning_service:
        return {"session_summary": None}

    session_summary = reasoning_service.compute_session_summary(session_objects)
    logger.info("Session summary: %s", session_summary.layer_counts)
    return {"session_summary": session_summary}


def route_node(state: GraphState) -> dict[str, Any]:
    """Set query_mode (doc_only | json_only | hybrid) and doc_only for LLM."""
    question = state.get("question", "")
    query_mode = routing.get_query_mode(question)
    doc_only = query_mode == "doc_only"
    if query_mode == "doc_only":
        logger.info("Query mode DOC_ONLY: definition-style question")
    elif query_mode == "json_only":
        logger.info("Query mode JSON_ONLY: counting/listing session objects, skip retrieval")
    else:
        logger.info("Query mode HYBRID: docs + session")
    return {"query_mode": query_mode, "doc_only": doc_only}


def retrieve_node(state: GraphState) -> dict[str, Any]:
    """Retrieve via retrieval_lc; skip retrieval for JSON_ONLY."""
    from ..retrieval_lc import retrieve

    settings = state.get("_settings")
    question = state.get("question", "")
    query_mode = state.get("query_mode", "hybrid")

    if not settings:
        return {"retrieved_docs": []}

    if query_mode == "json_only":
        return {"retrieved_docs": []}

    retrieved_docs = retrieve(
        query=question,
        top_k=settings.retrieval_top_k,
        max_distance=settings.retrieval_max_distance,
    )
    return {"retrieved_docs": retrieved_docs}


def llm_node(state: GraphState) -> dict[str, Any]:
    """Invoke LCEL chain (doc_only or hybrid)."""
    from ..lc.chains import invoke_doc_only, invoke_hybrid

    question = state.get("question", "")
    session_objects = state.get("session_objects", [])
    session_summary = state.get("session_summary")
    retrieved_docs = state.get("retrieved_docs", [])
    doc_only = state.get("doc_only", False)

    session_summary_dict = session_summary.model_dump() if session_summary else {}

    if doc_only:
        if not retrieved_docs:
            answer = "No explicit definition was found in the retrieved documents."
        else:
            answer = invoke_doc_only(question=question, retrieved_chunks=retrieved_docs)
    else:
        answer = invoke_hybrid(
            question=question,
            json_objects=session_objects,
            session_summary=session_summary_dict,
            retrieved_chunks=retrieved_docs,
        )
    return {"answer_text": answer}


def finalize_node(state: GraphState) -> dict[str, Any]:
    """For guard paths: set answer_text and session_summary. For main path: pass through."""
    guard_result = state.get("guard_result")
    reasoning_service = state.get("_reasoning_service")
    session_objects = state.get("session_objects", [])

    if guard_result:
        gr_type = guard_result.get("type")
        session_summary = state.get("session_summary")
        if session_summary is None and reasoning_service:
            session_summary = reasoning_service.compute_session_summary(session_objects)
        updates: dict[str, Any] = {}
        if session_summary is not None:
            updates["session_summary"] = session_summary
        if gr_type == "smalltalk":
            updates["answer_text"] = smalltalk.get_smalltalk_response(state.get("question", ""))
            return updates
        if gr_type == "missing_geometry":
            missing = guard_result.get("missing_layers", [])
            updates["answer_text"] = (
                f"Cannot determine because the current drawing does not provide geometric information "
                f"(coordinates/angles/distances) for: {', '.join(sorted(missing))}."
            )
            return updates
        if gr_type == "needs_input":
            missing_layers = guard_result.get("missing_layers", [])
            updates["answer_text"] = followups.build_needs_input_message(missing_layers)
            return updates
    return {}
