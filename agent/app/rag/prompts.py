"""Single source of truth for RAG prompt templates (strings). ChatPromptTemplates built in chains.py."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You are a careful assistant that answers user questions by combining:
(1) retrieved excerpts from planning/regulatory documents (persistent knowledge) and
(2) the current session's drawing object list in JSON (ephemeral state).

Rules:

1. Treat the retrieved document excerpts as authoritative. If a relevant rule is missing, say so.

2. Treat the JSON object list as the current ground truth for the drawing. Always use the latest JSON provided.

3. Do NOT invent objects, measurements, or rules.

4. **IMPORTANT**: Always analyze what CAN be determined from available geometry FIRST, even if some information is missing. Use the spatial analysis provided to understand relationships (e.g., property-highway fronting, distances).

5. Provide general rules and information that apply, even when specific details are missing. Be helpful and actionable.

6. If the question requires geometric computation and the JSON is insufficient (missing measurements, units, or reference points), explain what CAN be determined, then what cannot be determined, and what additional data is needed.

7. When you cite regulations, quote short phrases (not long passages). Do NOT include inline document references (e.g. [DocName_016_0032 | p16]) in your answer.

8. Return ONLY your direct answer. No "Evidence:" section, no inline document excerpts.

9. If the user's JSON is malformed or inconsistent, request a corrected JSON and explain what is wrong.

10. If required geometric data is missing (geometry is null / no coordinates), you must say it cannot be determined and must not infer spatial relationships. However, if geometry EXISTS, use it to provide useful analysis."""

# Human message template strings (used by chains.py to build ChatPromptTemplates)
HYBRID_HUMAN_TEMPLATE = """User question:
{question}

Session drawing objects (current JSON):
{json_objects_pretty}

Derived session summary (computed by the system):
- Layer counts: {layer_counts}
- Plot boundary present: {plot_boundary_present}
- Highways present: {highways_present}
- Known limitations: {limitations}
- Spatial analysis: {spatial_analysis}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
1. **FIRST**: Analyze what CAN be determined from the available geometry and spatial relationships (use the spatial analysis provided).
2. **SECOND**: Answer the user question using BOTH the retrieved excerpts and the current JSON.
3. **THIRD**: If the answer depends on geometry (e.g., "fronts a highway"), use the spatial analysis and explain your reasoning steps briefly.
4. **FOURTH**: If the rule depends on terms (e.g., "principal elevation", "highway"), prefer definitions in the retrieved excerpts.
5. **IMPORTANT**: Even if some information is missing, provide general rules and explain what CAN be determined from available data. Be helpful and actionable.

Return ONLY your direct answer:
- Start with what CAN be determined from available geometry (e.g., "Based on the coordinates, this property fronts a highway...").
- Then provide general rules from the documents that apply.
- Finally, if information is missing, be specific about what's needed (e.g., "For rear extensions, add a Walls layer with elevation='rear'").
- One or two paragraphs: your direct answer (short, direct).
- Do NOT include any inline document references (e.g. [DocName_016_0032 | p16]).
- If uncertain, state uncertainty and what additional data would resolve it."""

DOC_ONLY_HUMAN_TEMPLATE = """User question:
{question}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
Answer the question using ONLY the retrieved excerpts above. Do not refer to any drawing or session state unless the user explicitly asks about it.
- Quote short phrases from the excerpts where relevant.
- Do NOT include inline document references (e.g. [DocName_016_0032 | p16]).
Return ONLY your direct answer (no Evidence section, no preamble)."""


# --- Chunk formatting (used by chains and tests) ---

def format_chunk_for_prompt(chunk_id: str, source: str, page: str | None, section: str | None, text: str) -> str:
    """Format a retrieved chunk for the prompt."""
    page_str = f"p{page}" if page else "p?"
    section_str = f" | {section}" if section else ""
    return f"[DOC: {source} | {page_str} | chunk: {chunk_id}{section_str}]\n{text}"


# Alias for backward compatibility (same behavior as format_chunk_for_prompt).
format_chunk = format_chunk_for_prompt


def format_retrieved_chunks(chunks: list[dict]) -> str:
    """Format all retrieved chunks for the prompt."""
    if not chunks:
        return "No relevant excerpts found."
    formatted = []
    for chunk in chunks:
        formatted.append(format_chunk(
            chunk_id=chunk.get("id", "unknown"),
            source=chunk.get("source", "unknown"),
            page=chunk.get("page"),
            section=chunk.get("section"),
            text=chunk.get("text", "")
        ))
    return "\n\n".join(formatted)


_USER_PROMPT_TEMPLATE = """User question:
{question}

Session drawing objects (current JSON):
{json_objects_pretty}

Derived session summary (computed by the system):
- Layer counts: {layer_counts}
- Plot boundary present: {plot_boundary_present}
- Highways present: {highways_present}
- Known limitations: {limitations}
- Spatial analysis: {spatial_analysis}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
1. **FIRST**: Analyze what CAN be determined from the available geometry and spatial relationships (use the spatial analysis provided).
2. **SECOND**: Answer the user question using BOTH the retrieved excerpts and the current JSON.
3. **THIRD**: If the answer depends on geometry (e.g., "fronts a highway"), use the spatial analysis and explain your reasoning steps briefly.
4. **FOURTH**: If the rule depends on terms (e.g., "principal elevation", "highway"), prefer definitions in the retrieved excerpts.
5. **IMPORTANT**: Even if some information is missing, provide general rules and explain what CAN be determined from available data. Be helpful and actionable.

Return ONLY your direct answer:
- Start with what CAN be determined from available geometry (e.g., "Based on the coordinates, this property fronts a highway...").
- Then provide general rules from the documents that apply.
- Finally, if information is missing, be specific about what's needed (e.g., "For rear extensions, add a Walls layer with elevation='rear'").
- One or two paragraphs: your direct answer (short, direct).
- Do NOT include any inline document references (e.g. [DocName_016_0032 | p16]).
- If uncertain, state uncertainty and what additional data would resolve it."""

_USER_PROMPT_DOC_ONLY_TEMPLATE = """User question:
{question}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
Answer the question using ONLY the retrieved excerpts above. Do not refer to any drawing or session state unless the user explicitly asks about it.
- Quote short phrases from the excerpts where relevant.
- Do NOT include inline document references (e.g. [DocName_016_0032 | p16]).
Return ONLY your direct answer (no Evidence section, no preamble)."""


def build_user_prompt(
    question: str,
    json_objects: list[dict],
    session_summary: dict,
    retrieved_chunks: list[dict]
) -> str:
    """Build the complete user prompt (hybrid: question + JSON + summary + chunks)."""
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
    
    chunks_formatted = format_retrieved_chunks(retrieved_chunks)
    return _USER_PROMPT_TEMPLATE.format(
        question=question,
        json_objects_pretty=json_pretty,
        layer_counts=layer_counts_str,
        plot_boundary_present=session_summary.get("plot_boundary_present", False),
        highways_present=session_summary.get("highways_present", False),
        limitations=limitations_str,
        spatial_analysis=spatial_analysis_str,
        retrieved_chunks_formatted=chunks_formatted,
    )


def build_user_prompt_doc_only(question: str, retrieved_chunks: list[dict]) -> str:
    """Build user prompt for definition-only questions: question + retrieved chunks only."""
    chunks_formatted = format_retrieved_chunks(retrieved_chunks)
    return _USER_PROMPT_DOC_ONLY_TEMPLATE.format(
        question=question,
        retrieved_chunks_formatted=chunks_formatted,
    )
