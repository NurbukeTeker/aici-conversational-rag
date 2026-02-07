"""LangChain ChatPromptTemplate equivalents for hybrid RAG (content same as existing prompts)."""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = """You are a careful assistant that answers user questions by combining:
(1) retrieved excerpts from planning/regulatory documents (persistent knowledge) and
(2) the current session's drawing object list in JSON (ephemeral state).

Rules:

1. Treat the retrieved document excerpts as authoritative. If a relevant rule is missing, say so.

2. Treat the JSON object list as the current ground truth for the drawing. Always use the latest JSON provided.

3. Do NOT invent objects, measurements, or rules.

4. If the question requires geometric computation and the JSON is insufficient (missing measurements, units, or reference points), explain what cannot be determined and what additional data is needed.

5. When you cite regulations, quote short phrases (not long passages). Do NOT include inline document references (e.g. [DocName_016_0032 | p16]) in your answer.

6. Return ONLY your direct answer. No "Evidence:" section, no inline document excerpts.

7. If the user's JSON is malformed or inconsistent, request a corrected JSON and explain what is wrong.

8. If required geometric data is missing (geometry is null / no coordinates), you must say it cannot be determined and must not infer spatial relationships."""


# Hybrid: question + session JSON + session summary + retrieved chunks
HYBRID_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """User question:
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
- Do NOT include any inline document references (e.g. [DocName_016_0032 | p16]).
- If uncertain, state uncertainty and what additional data would resolve it.""")
])

# Doc-only: question + retrieved chunks only (no session JSON/summary)
DOC_ONLY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """User question:
{question}

Retrieved regulatory excerpts (persistent knowledge):
{retrieved_chunks_formatted}

Task:
Answer the question using ONLY the retrieved excerpts above. Do not refer to any drawing or session state unless the user explicitly asks about it.
- Quote short phrases from the excerpts where relevant.
- Do NOT include inline document references (e.g. [DocName_016_0032 | p16]).
Return ONLY your direct answer (no Evidence section, no preamble).""")
])


def format_chunk_for_prompt(chunk_id: str, source: str, page: str | None, section: str | None, text: str) -> str:
    """Format a retrieved chunk for the prompt (same as prompts.format_chunk)."""
    page_str = f"p{page}" if page else "p?"
    section_str = f" | {section}" if section else ""
    return f"[DOC: {source} | {page_str} | chunk: {chunk_id}{section_str}]\n{text}"
