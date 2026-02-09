"""LCEL Runnables: doc_only_chain and hybrid_chain with sync + astream helpers."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence
from langchain_openai import ChatOpenAI

from langchain_core.prompts import ChatPromptTemplate

from .prompts import (
    SYSTEM_PROMPT,
    HYBRID_HUMAN_TEMPLATE,
    DOC_ONLY_HUMAN_TEMPLATE,
    format_chunk_for_prompt,
)

HYBRID_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", HYBRID_HUMAN_TEMPLATE),
])
DOC_ONLY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", DOC_ONLY_HUMAN_TEMPLATE),
])

logger = logging.getLogger(__name__)

doc_only_chain: RunnableSequence | None = None
hybrid_chain: RunnableSequence | None = None


def build_chains(
    model: str = "gpt-4o",
    api_key: str = "",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> tuple[RunnableSequence, RunnableSequence]:
    """Build and return (doc_only_chain, hybrid_chain)."""
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key or None,
    )
    doc_chain = DOC_ONLY_PROMPT | llm | StrOutputParser()
    hybrid_chain_inst = HYBRID_PROMPT | llm | StrOutputParser()
    global doc_only_chain, hybrid_chain
    doc_only_chain = doc_chain
    hybrid_chain = hybrid_chain_inst
    return doc_chain, hybrid_chain_inst


# Message when no chunks for doc_only (no hallucination).
DOC_ONLY_EMPTY_MESSAGE = "No explicit definition was found in the retrieved documents."


def _format_retrieved_chunks(chunks: list[dict], empty_message: str | None = None) -> str:
    """Format retrieved chunks for prompt."""
    if not chunks:
        return empty_message or "No relevant excerpts found."
    formatted = []
    for c in chunks:
        formatted.append(format_chunk_for_prompt(
            chunk_id=c.get("id", c.get("chunk_id", "unknown")),
            source=c.get("source", "unknown"),
            page=c.get("page"),
            section=c.get("section"),
            text=c.get("text", c.get("page_content", "")),
        ))
    return "\n\n".join(formatted)


def invoke_doc_only(question: str, retrieved_chunks: list[dict]) -> str:
    """Sync invoke doc_only_chain."""
    if not doc_only_chain:
        raise RuntimeError("Chains not built; call build_chains() first")
    chunks_fmt = _format_retrieved_chunks(retrieved_chunks, empty_message=DOC_ONLY_EMPTY_MESSAGE)
    return doc_only_chain.invoke({
        "question": question,
        "retrieved_chunks_formatted": chunks_fmt,
    })


def invoke_hybrid(
    question: str,
    json_objects: list[dict],
    session_summary: dict,
    retrieved_chunks: list[dict],
) -> str:
    """Sync invoke hybrid_chain."""
    if not hybrid_chain:
        raise RuntimeError("Chains not built; call build_chains() first")
    json_pretty = json.dumps(json_objects, indent=2) if json_objects else "[]"
    layer_counts = session_summary.get("layer_counts", {})
    layer_counts_str = ", ".join(f"{k}={v}" for k, v in layer_counts.items()) if layer_counts else "None"
    limitations = session_summary.get("limitations", [])
    limitations_str = ", ".join(limitations) if limitations else "None"
    
    # Format spatial analysis for prompt
    spatial_analysis = session_summary.get("spatial_analysis")
    if spatial_analysis:
        spatial_str_parts = []
        if spatial_analysis.get("property_highway_analysis"):
            pha = spatial_analysis["property_highway_analysis"]
            spatial_str_parts.append(f"Property-Highway: {pha.get('analysis', 'N/A')}")
        if spatial_analysis.get("available_geometry"):
            spatial_str_parts.append(f"Layers with geometry: {', '.join(spatial_analysis['available_geometry'])}")
        if spatial_analysis.get("missing_for_extensions"):
            spatial_str_parts.append(f"Missing for extensions: {', '.join(spatial_analysis['missing_for_extensions'])}")
        spatial_analysis_str = "; ".join(spatial_str_parts) if spatial_str_parts else "None"
    else:
        spatial_analysis_str = "None"
    
    chunks_fmt = _format_retrieved_chunks(retrieved_chunks)
    return hybrid_chain.invoke({
        "question": question,
        "json_objects_pretty": json_pretty,
        "layer_counts": layer_counts_str,
        "plot_boundary_present": session_summary.get("plot_boundary_present", False),
        "highways_present": session_summary.get("highways_present", False),
        "limitations": limitations_str,
        "spatial_analysis": spatial_analysis_str,
        "retrieved_chunks_formatted": chunks_fmt,
    })


async def astream_doc_only(question: str, retrieved_chunks: list[dict]):
    """Async stream doc_only_chain tokens."""
    if not doc_only_chain:
        raise RuntimeError("Chains not built; call build_chains() first")
    chunks_fmt = _format_retrieved_chunks(retrieved_chunks, empty_message=DOC_ONLY_EMPTY_MESSAGE)
    async for chunk in doc_only_chain.astream({
        "question": question,
        "retrieved_chunks_formatted": chunks_fmt,
    }):
        yield chunk


async def astream_hybrid(
    question: str,
    json_objects: list[dict],
    session_summary: dict,
    retrieved_chunks: list[dict],
):
    """Async stream hybrid_chain tokens."""
    if not hybrid_chain:
        raise RuntimeError("Chains not built; call build_chains() first")
    json_pretty = json.dumps(json_objects, indent=2) if json_objects else "[]"
    layer_counts = session_summary.get("layer_counts", {})
    layer_counts_str = ", ".join(f"{k}={v}" for k, v in layer_counts.items()) if layer_counts else "None"
    limitations = session_summary.get("limitations", [])
    limitations_str = ", ".join(limitations) if limitations else "None"
    chunks_fmt = _format_retrieved_chunks(retrieved_chunks)
    async for chunk in hybrid_chain.astream({
        "question": question,
        "json_objects_pretty": json_pretty,
        "layer_counts": layer_counts_str,
        "plot_boundary_present": session_summary.get("plot_boundary_present", False),
        "highways_present": session_summary.get("highways_present", False),
        "limitations": limitations_str,
        "retrieved_chunks_formatted": chunks_fmt,
    }):
        yield chunk
