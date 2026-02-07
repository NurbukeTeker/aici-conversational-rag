# Verification Report: Full LangChain + LangGraph Pipeline

**Branch:** feature/full-langchain-langgraph  
**Date:** 2025-02-07

## 1. Implementation status (feature/full-langchain-langgraph)

| Item | Status | Notes |
|------|--------|------|
| **agent/app/lc/prompts.py** | ✅ | ChatPromptTemplate for hybrid + doc_only; content aligned with existing prompts |
| **agent/app/lc/chains.py** | ✅ | LCEL doc_only_chain, hybrid_chain; invoke + astream_doc_only / astream_hybrid |
| **agent/app/retrieval_lc.py** | ✅ | LangChain Chroma (get_vectorstore, as_retriever); retrieve() uses similarity_search_with_score + postprocess |
| **agent/app/graph_lc/state.py** | ✅ | GraphState TypedDict (question, session_objects, session_summary, doc_only, retrieved_docs, answer_text, evidence, guard_result) |
| **agent/app/graph_lc/nodes.py** | ✅ | validate, smalltalk, geometry_guard, followup, summarize, retrieve, route, llm, evidence, finalize |
| **agent/app/graph_lc/graph_builder.py** | ✅ | StateGraph with conditional edges; run_graph_until_route() for streaming |
| **main.py /answer** | ✅ | Uses answer_graph.invoke() only; returns AnswerResponse(answer, evidence, session_summary) |
| **main.py /answer/stream** | ✅ | Uses run_graph_until_route() + graph nodes; streams via LCEL astream; evidence/finalize then NDJSON done |
| **API contract** | ✅ | POST /answer → AnswerResponse; POST /answer/stream → NDJSON t:chunk (c:...) then t:done |
| **Session** | ✅ | Stateless; session_objects per request |
| **Evidence shape** | ✅ | document_chunks (chunk_id, source, page, snippet); session_objects (layers_used, object_indices, object_labels) |
| **Ingestion** | ✅ | RecursiveCharacterTextSplitter; vector_store.add_documents (chunk_id, metadata); sync unchanged |
| **Dependencies** | ✅ | langchain-core, langchain-openai, langchain-text-splitters, langchain-chroma, langgraph, chromadb, pypdf; no langchain_community |

## 2. Cleanup checklist (must remove / must keep)

### Removed or refactored

- **Procedural pipeline in /answer**  
  Removed. `/answer` uses only `answer_graph.invoke(initial_state)`.

- **Procedural pipeline in /answer/stream**  
  Removed. Streaming uses the same node logic as the graph:
  - `run_graph_until_route(request, reasoning_service, settings)` runs validate → smalltalk → geometry_guard → followup → summarize → retrieve → route.
  - Guard path: `graph_nodes.finalize_node(state)` then emit chunk + done.
  - Main path: LCEL `astream_doc_only` / `astream_hybrid`, then `evidence_node` + `finalize_node`, then emit done.
  - No duplicated smalltalk/geometry/followup/retrieve/route logic in main.

- **LLMService / legacy LLM “pipeline glue”**  
  Removed. `agent/app/llm_service.py` deleted. LLM invocation is only via LCEL chains in `agent/app/lc/chains.py`.

- **Direct chromadb retrieval for /answer**  
  Not used for answers. Answer path uses `retrieval_lc` (LangChain Chroma + similarity_search_with_score / postprocess). `vector_store.py` is used only for sync/ingestion and health (count, is_ready).

### Kept (domain / ingestion)

- **smalltalk, geometry_guard, followups**  
  Used inside graph nodes only; no duplication in main.

- **ReasoningService**  
  Session summary, extract_layers_used, validation; used in graph nodes.

- **Prompt content**  
  Same logic; implementation is ChatPromptTemplate in `lc/prompts.py`.

- **retrieval.py**  
  Kept. Contains only `postprocess_retrieved_chunks` (distance/dedupe); used by `retrieval_lc`. Domain helper, not “retrieval pipeline”.

- **vector_store.py (VectorStoreService)**  
  Kept for sync and health: add_documents, delete_by_ids, count, is_ready. Not used for /answer retrieval.

## 3. Six-point verification

| Check | Result |
|-------|--------|
| **A) /answer source of truth** | ✅ `main.py` calls `answer_graph.invoke(initial_state)` only; no procedural steps. |
| **B) Retrieval for answers** | ✅ Answer path uses `retrieval_lc` (LangChain Chroma). No direct `collection.query` in answer flow. |
| **C) LLM invocation** | ✅ Runnable chains in `lc/chains.py` (prompt \| llm \| StrOutputParser); no LLMService. |
| **D) Unused/duplicate services** | ✅ `llm_service.py` removed. No duplicate “pipeline” layer. |
| **E) Streaming** | ✅ `/answer/stream` uses graph nodes (run_graph_until_route) + LCEL astream + evidence/finalize; NDJSON format unchanged. |
| **F) requirements and imports** | ✅ LangChain/LangGraph packages in use; no unused langchain_community. |

## 4. Grep confirmation (no legacy pipeline references)

- `graph.invoke` / `answer_graph.invoke`: used in `main.py` for `/answer`.
- `run_graph_until_route`: used in `main.py` for `/answer/stream`.
- No remaining references to `LLMService`, `generate_answer`, or a legacy `/answer` procedural pipeline.
- `_stream_answer_ndjson`: name kept as the streaming generator; implementation is graph-node + LCEL based.

## 5. Tests

- **test_graph.py**
  - Smalltalk: no retrieval/LLM.
  - Geometry guard: deterministic message, no retrieval/LLM.
  - Followup “what it needs?”: deterministic checklist, no retrieval/LLM.
  - Doc-only: doc_only_chain, no object evidence.
  - Hybrid: retriever + hybrid chain, evidence with chunks and layers.
  - **Stream:** `/answer/stream` returns 200, NDJSON lines, last line `t: "done"` with `answer`, `evidence`, `session_summary`.

## 6. Summary

- **Single source of truth:** Answer and stream flows are driven by the LangGraph workflow and LCEL chains. No remaining legacy procedural pipeline in `/answer` or `/answer/stream`.
- **Retrieval:** Answer retrieval is LangChain Chroma via `retrieval_lc`; direct chromadb is only in sync/ingestion (`vector_store.py`).
- **LLM:** Only LCEL chains; `llm_service.py` removed.
- **Streaming:** Same node sequence as the graph up to route; then LCEL astream and graph evidence/finalize; NDJSON contract preserved.
