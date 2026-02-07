"""Build and compile LangGraph StateGraph for hybrid RAG."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import StateGraph, END

from .state import GraphState
from . import nodes

if TYPE_CHECKING:
    from ..reasoning import ReasoningService
    from ..config import Settings
    from ..models import AnswerRequest


def build_answer_graph(
    reasoning_service: "ReasoningService",
    settings: "Settings",
):
    """Build and compile the LangGraph for hybrid RAG."""

    def _inject(state: GraphState) -> GraphState:
        state["_reasoning_service"] = reasoning_service
        state["_settings"] = settings
        return state

    def validate(s: GraphState):
        _inject(dict(s))
        return nodes.validate_node(s)

    def smalltalk(s: GraphState):
        _inject(dict(s))
        return nodes.smalltalk_node(s)

    def geometry_guard(s: GraphState):
        _inject(dict(s))
        return nodes.geometry_guard_node(s)

    def followup(s: GraphState):
        _inject(dict(s))
        return nodes.followup_node(s)

    def summarize(s: GraphState):
        _inject(dict(s))
        return nodes.summarize_node(s)

    def retrieve(s: GraphState):
        _inject(dict(s))
        return nodes.retrieve_node(s)

    def route(s: GraphState):
        _inject(dict(s))
        return nodes.route_node(s)

    def llm(s: GraphState):
        _inject(dict(s))
        return nodes.llm_node(s)

    def finalize(s: GraphState):
        _inject(dict(s))
        return nodes.finalize_node(s)

    workflow = StateGraph(GraphState)
    workflow.add_node("validate", validate)
    workflow.add_node("smalltalk", smalltalk)
    workflow.add_node("geometry_guard", geometry_guard)
    workflow.add_node("followup", followup)
    workflow.add_node("summarize", summarize)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("route", route)
    workflow.add_node("llm", llm)
    workflow.add_node("finalize", finalize)

    workflow.set_entry_point("validate")
    workflow.add_edge("validate", "smalltalk")

    def after_smalltalk(s: GraphState):
        if s.get("guard_result"):
            return "finalize"
        return "geometry_guard"

    workflow.add_conditional_edges("smalltalk", after_smalltalk)
    workflow.add_edge("geometry_guard", "followup")

    def after_followup(s: GraphState):
        if s.get("guard_result") and s["guard_result"].get("type") == "missing_geometry":
            return "finalize"
        if s.get("guard_result") and s["guard_result"].get("type") == "needs_input":
            return "finalize"
        return "summarize"

    workflow.add_conditional_edges("followup", after_followup)
    workflow.add_edge("summarize", "route")
    workflow.add_edge("route", "retrieve")
    workflow.add_edge("retrieve", "llm")
    workflow.add_edge("llm", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile(checkpointer=None)


def run_graph_until_route(
    request: "AnswerRequest",
    reasoning_service: "ReasoningService",
    settings: "Settings",
) -> dict[str, Any]:
    """
    Run graph nodes validate -> smalltalk -> geometry_guard -> followup -> summarize -> retrieve -> route.
    Returns state dict. Used by /answer/stream so streaming uses the same node logic (single source of truth).
    """
    state: dict[str, Any] = {
        "question": request.question,
        "session_objects": request.session_objects,
        "_reasoning_service": reasoning_service,
        "_settings": settings,
    }
    state.update(nodes.validate_node(state))
    state.update(nodes.smalltalk_node(state))
    if state.get("guard_result"):
        return state
    state.update(nodes.geometry_guard_node(state))
    if state.get("guard_result"):
        return state
    state.update(nodes.followup_node(state))
    if state.get("guard_result"):
        return state
    state.update(nodes.summarize_node(state))
    state.update(nodes.route_node(state))
    state.update(nodes.retrieve_node(state))
    return state
