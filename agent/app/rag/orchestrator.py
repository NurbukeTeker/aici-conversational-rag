"""Answer orchestration: run_answer (sync) and stream_answer_ndjson (async generator)."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..models import AnswerRequest, AnswerResponse

logger = logging.getLogger(__name__)


def _state_to_done_payload(state: dict[str, Any]) -> dict:
    """Build NDJSON done payload from graph state."""
    session_summary = state.get("session_summary")
    if session_summary is not None and hasattr(session_summary, "model_dump"):
        session_summary = session_summary.model_dump()
    return {
        "t": "done",
        "answer": state.get("answer_text", ""),
        "query_mode": state.get("query_mode"),
        "session_summary": session_summary,
    }


def run_answer(request: AnswerRequest, answer_graph: Any) -> AnswerResponse:
    """Run the LangGraph workflow and return AnswerResponse."""
    initial_state = {
        "question": request.question,
        "session_objects": request.session_objects,
    }
    final_state = answer_graph.invoke(initial_state)
    return AnswerResponse(
        answer=final_state.get("answer_text", ""),
        query_mode=final_state.get("query_mode"),
        session_summary=final_state.get("session_summary"),
    )


async def stream_answer_ndjson(
    request: AnswerRequest,
    reasoning_service: Any,
    settings: Any,
):
    """
    Async generator: run graph nodes until route, stream LLM via LCEL astream, then finalize.
    Yields NDJSON lines: {"t":"chunk","c":"..."} then {"t":"done", ...}. On exception yields {"t":"error","message":"..."}.
    """
    from ..graph_lc import run_graph_until_route
    from ..graph_lc import nodes as graph_nodes
    from .chains import DOC_ONLY_EMPTY_MESSAGE, astream_doc_only, astream_hybrid
    from ..guards.doc_only_guard import should_use_retrieved_for_doc_only

    try:
        state = run_graph_until_route(request, reasoning_service, settings)

        if state.get("guard_result"):
            state.update(graph_nodes.finalize_node(state))
            answer_text = state.get("answer_text", "")
            yield json.dumps({"t": "chunk", "c": answer_text}) + "\n"
            yield json.dumps(_state_to_done_payload(state)) + "\n"
            return

        retrieved_docs = state.get("retrieved_docs", [])
        doc_only = state.get("doc_only", False)
        session_summary = state.get("session_summary")
        session_summary_dict = session_summary.model_dump() if session_summary else {}

        full_answer_chunks = []
        if doc_only:
            if not retrieved_docs or not should_use_retrieved_for_doc_only(request.question, retrieved_docs):
                override_msg = DOC_ONLY_EMPTY_MESSAGE
                state["answer_text"] = override_msg
                yield json.dumps({"t": "chunk", "c": override_msg}) + "\n"
            else:
                async for chunk in astream_doc_only(request.question, retrieved_docs):
                    full_answer_chunks.append(chunk)
                    yield json.dumps({"t": "chunk", "c": chunk}) + "\n"
                state["answer_text"] = "".join(full_answer_chunks)
        else:
            async for chunk in astream_hybrid(
                request.question,
                request.session_objects,
                session_summary_dict,
                retrieved_docs,
            ):
                full_answer_chunks.append(chunk)
                yield json.dumps({"t": "chunk", "c": chunk}) + "\n"
            state["answer_text"] = "".join(full_answer_chunks)

        state.update(graph_nodes.finalize_node(state))
        yield json.dumps(_state_to_done_payload(state)) + "\n"
    except Exception as e:
        logger.exception("Error streaming answer: %s", e)
        yield json.dumps({"t": "error", "message": str(e)}) + "\n"
