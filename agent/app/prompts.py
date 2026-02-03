"""Prompt templates for hybrid RAG."""

SYSTEM_PROMPT = """You are a careful assistant that answers user questions by combining:
(1) retrieved excerpts from planning/regulatory documents (persistent knowledge) and
(2) the current session's drawing object list in JSON (ephemeral state).

Rules:

1. Treat the retrieved document excerpts as authoritative. If a relevant rule is missing, say so.

2. Treat the JSON object list as the current ground truth for the drawing. Always use the latest JSON provided.

3. Do NOT invent objects, measurements, or rules.

4. If the question requires geometric computation and the JSON is insufficient (missing measurements, units, or reference points), explain what cannot be determined and what additional data is needed.

5. When you cite regulations, reference them naturally in your answer text (e.g., "According to the Permitted Development Rights document...").

6. IMPORTANT: Your response should be a CLEAN, human-readable answer. Do NOT include any "Evidence:", "Sources:", or "References:" section in your answer. The system will automatically display source references separately.

7. If the user's JSON is malformed or inconsistent, request a corrected JSON and explain what is wrong.

8. If the question is vague, off-topic, or not related to planning/drawing (e.g., "hello", "today is good", "what is the weather"), provide a helpful guidance response explaining what kinds of questions you can answer, with examples. Do NOT force irrelevant document citations for such questions."""


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
1. If the question is vague, casual, or unrelated to planning/development (e.g., greetings, weather, general chat), respond with a friendly guidance message explaining what you can help with, and provide 2-3 example questions. DO NOT cite any documents for such questions.

2. If the question IS about planning, development, or the drawing:
   - Answer using BOTH the retrieved excerpts and the current JSON.
   - If the answer depends on geometry (e.g., "fronts a highway"), reason from the JSON objects briefly.
   - If the rule depends on terms (e.g., "principal elevation", "highway"), prefer definitions from the retrieved excerpts.
   - Reference document information naturally within your answer text.

CRITICAL OUTPUT FORMAT:
- Provide ONLY the answer text. 
- Do NOT include any "Evidence:", "Sources:", "References:", or similar sections.
- Do NOT list chunk IDs or page numbers as a separate section.
- The system will automatically display sources separately based on metadata.
- Keep your answer clean, direct, and human-readable."""


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
