"""Prompt templates for hybrid RAG."""

SYSTEM_PROMPT = """You are a careful assistant that answers user questions by combining:
(1) retrieved excerpts from planning/regulatory documents (persistent knowledge) and
(2) the current session's drawing object list in JSON (ephemeral state).

Rules:

1. Treat the retrieved document excerpts as authoritative. If a relevant rule is missing, say so.

2. Treat the JSON object list as the current ground truth for the drawing. Always use the latest JSON provided.

3. Do NOT invent objects, measurements, or rules.

4. If the question requires geometric computation and the JSON is insufficient (missing measurements, units, or reference points), explain what cannot be determined and what additional data is needed.

5. When you cite regulations, quote short phrases (not long passages). Do NOT include inline document references (e.g. [DocName_016_0032 | p16]) in your answer — the Evidence panel below shows these.

6. Return ONLY your direct answer. No "Evidence:" section, no inline document excerpts. End your answer with exactly: "Relevant documents and JSON layers used are listed in the Evidence section below."

7. If the user's JSON is malformed or inconsistent, request a corrected JSON and explain what is wrong.

8. If required geometric data is missing (geometry is null / no coordinates), you must say it cannot be determined and must not infer spatial relationships."""


USER_PROMPT_TEMPLATE = """User question:
{question}

Session drawing objects (current JSON):
{json_objects_pretty}

Derived session summary (computed by the system):
- Layer counts: {layer_counts}
- Plot boundary present: {plot_boundary_present}
- Highways present: {highways_present}
- Known limitations: {limitations}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
1. Answer the user question using BOTH the retrieved excerpts and the current JSON.
2. If the answer depends on geometry (e.g., "fronts a highway"), reason from the JSON objects and explain your reasoning steps briefly.
3. If the rule depends on terms (e.g., "principal elevation", "highway"), prefer definitions in the retrieved excerpts.

Return ONLY your direct answer:
- One or two paragraphs: your direct answer (short, direct).
- Do NOT include any inline document references (e.g. [DocName_016_0032 | p16]) — the Evidence panel shows them.
- If uncertain, state uncertainty and what additional data would resolve it.
- End with exactly: "Relevant documents and JSON layers used are listed in the Evidence section below." """


# Doc-only prompt: definition questions — no session JSON or session summary in prompt
USER_PROMPT_DOC_ONLY_TEMPLATE = """User question:
{question}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
Answer the question using ONLY the retrieved excerpts above. Do not refer to any drawing or session state unless the user explicitly asks about it.
- Quote short phrases from the excerpts where relevant.
- Do NOT include inline document references (e.g. [DocName_016_0032 | p16]) — the Evidence panel shows them.
- End with exactly: "Relevant documents and JSON layers used are listed in the Evidence section below."
Return ONLY your direct answer (no Evidence section, no preamble)."""


def format_chunk(chunk_id: str, source: str, page: str | None, section: str | None, text: str) -> str:
    """Format a retrieved chunk for the prompt."""
    page_str = f"p{page}" if page else "p?"
    section_str = f" | {section}" if section else ""
    return f"[DOC: {source} | {page_str} | chunk: {chunk_id}{section_str}]\n{text}"


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


def build_user_prompt(
    question: str,
    json_objects: list[dict],
    session_summary: dict,
    retrieved_chunks: list[dict]
) -> str:
    """Build the complete user prompt."""
    import json
    
    json_pretty = json.dumps(json_objects, indent=2) if json_objects else "[]"
    
    layer_counts = session_summary.get("layer_counts", {})
    layer_counts_str = ", ".join(f"{k}={v}" for k, v in layer_counts.items()) if layer_counts else "None"
    
    limitations = session_summary.get("limitations", [])
    limitations_str = ", ".join(limitations) if limitations else "None"
    
    chunks_formatted = format_retrieved_chunks(retrieved_chunks)
    
    return USER_PROMPT_TEMPLATE.format(
        question=question,
        json_objects_pretty=json_pretty,
        layer_counts=layer_counts_str,
        plot_boundary_present=session_summary.get("plot_boundary_present", False),
        highways_present=session_summary.get("highways_present", False),
        limitations=limitations_str,
        retrieved_chunks_formatted=chunks_formatted
    )


def build_user_prompt_doc_only(question: str, retrieved_chunks: list[dict]) -> str:
    """Build user prompt for definition-only questions: question + retrieved chunks only (no JSON/session summary)."""
    chunks_formatted = format_retrieved_chunks(retrieved_chunks)
    return USER_PROMPT_DOC_ONLY_TEMPLATE.format(
        question=question,
        retrieved_chunks_formatted=chunks_formatted
    )
