# Agent Code Guide

Folder-level, file-by-file documentation for `agent/app/`. All claims are derived from actual code.

**Current layout (post-refactor):** Single source of truth for the agent. **API** in `main.py` (thin controllers). **Orchestration** in `rag/orchestrator.py`. **Graph** in `graph_lc/` (LangGraph StateGraph). **RAG** in `rag/` (prompts, LCEL chains, retrieval, retrieval_postprocess). **Guards** in `guards/` (doc_only_guard, geometry_guard). **Ingestion** in `ingest/` (ingestion.py). Shared modules at app root: config, models, chroma_client, vector_store, document_registry, sync_service, reasoning, routing, smalltalk, followups.

---

## agent/app/__init__.py

**Purpose:** Package marker. Contains only a docstring describing the agent.

**Key symbols:** None.

**Callers:** Python package loader.

---

## agent/app/config.py

**Purpose:** Centralizes agent configuration via Pydantic Settings loaded from environment variables.

**Key classes/functions:**
- `Settings` — openai_api_key, openai_model, chroma_persist_directory, chroma_collection_name, pdf_data_directory, retrieval_top_k, retrieval_max_distance, chunk_size, chunk_overlap.
- `get_settings()` — Cached settings instance (lru_cache).

**Inputs/outputs:**
- Inputs: Environment variables, `.env` file.
- Outputs: `Settings` instance with defaults (e.g. `retrieval_top_k=5`, `chunk_size=1000`, `chunk_overlap=200`).

**Callers:** chroma_client, ingest.ingestion, rag.retrieval, sync_service, vector_store, main, graph_lc (via injection).

**Edge cases / errors:** `extra="ignore"`. `retrieval_max_distance` default None (no distance filter).

---

## agent/app/chroma_client.py

**Purpose:** Shared ChromaDB PersistentClient to avoid multiple clients with different settings. Used by ingestion and retrieval.

**Key functions:**
- `get_chroma_client()` — Singleton PersistentClient at `chroma_persist_directory`. Settings: anonymized_telemetry=False, allow_reset=True.

**Inputs/outputs:**
- Inputs: `CHROMA_PERSIST_DIRECTORY` from config.
- Outputs: `chromadb.PersistentClient` instance.

**Callers:** `vector_store.py`, `rag/retrieval.py`.

**Edge cases / errors:** Directory created with `mkdir(parents=True, exist_ok=True)`.

**Potential refactors:** Single global client; consider context manager for tests. No explicit embedding model configuration; relies on Chroma default.

---

## agent/app/vector_store.py

**Purpose:** ChromaDB vector store operations: add documents, search, delete by ids/source, count. Uses shared Chroma client.

**Key classes/functions:**
- `VectorStoreService` — `add_documents`, `search`, `count`, `clear`, `delete_by_ids`, `delete_by_source`, `is_ready`.
- Metadata filtered to exclude None (Chroma rejects None).

**Inputs/outputs:**
- `add_documents(chunks)`: chunks = list of `{id, text, metadata}`. Batches of 100.
- `search(query, top_k)`: returns list of `{id, text, source, page, section, distance}`.
- `delete_by_source(source)`: where clause on source; deletes matching ids.

**Callers:** `sync_service.py` (add_documents, delete_by_ids, count, clear).

**Edge cases / errors:** Empty chunks return 0 added. Empty collection search returns []. Exceptions logged; delete_by_ids/delete_by_source return 0 on error.

**Note:** Sync uses VectorStoreService; Q&A retrieval uses `rag/retrieval.py` (LangChain Chroma). Both use the same chroma_client.

---

## agent/app/ingest/ingestion.py

**Purpose:** PDF text extraction (pypdf), chunking (RecursiveCharacterTextSplitter), and metadata attachment. Produces chunks for vector store.

**Key classes/functions:**
- `PDFIngestionService` — `get_pdf_files`, `extract_text_from_pdf`, `detect_section`, `chunk_pages`, `ingest_all`, `get_chunks_for_storage`.
- `RecursiveCharacterTextSplitter` — chunk_size, chunk_overlap from config; separators `["\n\n", "\n", ". ", " ", ""]`.

**Inputs/outputs:**
- `extract_text_from_pdf`: Path; outputs list of `{page_num, text, source}`.
- `chunk_pages`: pages list; yields `{id, text, metadata}` with source, page, chunk_index, chunk_id, section (if detected).
- `detect_section`: Looks for patterns like "Class A", "General Issues", etc. in first 200 chars.

**Callers:** `sync_service.py` (imports `PDFIngestionService` from `ingest.ingestion`). Package `ingest/__init__.py` re-exports `PDFIngestionService`.


**Edge cases / errors:** Non-existent PDF directory returns []. Extract exceptions logged; returns []. Section detection returns None if no match.

---

## agent/app/document_registry.py

**Purpose:** Tracks ingested PDFs by source_id, content_hash, chunk_ids for incremental sync. Persists to JSON file.

**Key classes/functions:**
- `DocumentStatus` — Enum: NEW, UNCHANGED, UPDATED, DELETED.
- `DocumentRecord` — source_id, content_hash, chunk_ids, version, last_ingested_at, page_count, chunk_count.
- `DocumentRegistry` — `compute_hash`, `get_status`, `get_deleted_sources`, `register`, `unregister`, `get_chunk_ids`, `get_all_records`, `clear`.
- `compute_hash(file_path)` — SHA256 of file contents (8KB chunks).

**Inputs/outputs:**
- `get_status(source_id, content_hash)`: returns DocumentStatus.
- `register(source_id, content_hash, chunk_ids, page_count)`: updates/creates record; increments version.
- `unregister(source_id)`: returns chunk_ids for deletion.

**Callers:** `sync_service.py`. Registry path: `{chroma_persist_directory}/document_registry.json`.

**Edge cases / errors:** Load failure starts fresh; save on every register/unregister/clear.

**Potential refactors:** Registry and Chroma in same directory; consider separate path. No locking; concurrent writes could corrupt.

---

## agent/app/sync_service.py

**Purpose:** Incremental document sync: NEW/UNCHANGED/UPDATED/DELETED. Orchestrates ingestion, registry, vector store.

**Key classes/functions:**
- `SyncResult` — new_documents, updated_documents, unchanged_documents, deleted_documents, total_chunks_added/deleted, errors.
- `DocumentSyncService` — `sync(delete_missing)`, `force_reingest(source_id)`, `get_status`.
- `_process_document` — Hash → status; UNCHANGED skip; UPDATED delete old chunks; ingest and register.
- `_delete_document` — Unregister and delete chunks for missing files.

**Inputs/outputs:**
- `sync(delete_missing=False)`: Processes all PDFs; optional deletion of registry entries for missing files.
- `force_reingest(source_id)`: Unregisters specific or all docs; re-ingests.

**Callers:** `main.py` (startup sync, /ingest endpoint). Imports `PDFIngestionService` from `ingest.ingestion`.

**Edge cases / errors:** Per-document errors appended to SyncResult.errors; processing continues. Empty chunks logged and skipped.

**Potential refactors:** `force_reingest(None)` clears entire registry and vector store; may be heavy for large corpuses.

---

## agent/app/rag/retrieval_postprocess.py

**Purpose:** Pure Python postprocessing of retrieved chunks (no LangChain). Filter by max_distance, limit per (source, page), sort by distance. Used by retrieval and by tests without pulling in LangChain.

**Key functions:**
- `postprocess(chunks, max_distance, max_per_page)` — Filters by distance threshold; keeps up to 2 chunks per (source, page); sorts by distance ascending.

**Constants:** `MAX_CHUNKS_PER_PAGE=2`, `_DISTANCE_NONE=inf` for missing distance.

**Inputs/outputs:**
- Input: list of chunk dicts with `distance`, `source`, `page`.
- Output: filtered, deduplicated, sorted list.

**Callers:** `rag/retrieval.py`, `agent/tests/test_retrieval.py`.

**Edge cases / errors:** None/invalid distance treated as inf (sorted last).

---

## agent/app/rag/retrieval.py

**Purpose:** LangChain Chroma retrieval. similarity_search_with_score, then postprocess (from retrieval_postprocess). Same collection as ingestion.

**Key functions:**
- `get_vectorstore()` — LangChain Chroma with shared client, collection from config.
- `retrieve(query, top_k, max_distance)` — similarity_search_with_score → postprocess; returns list of chunk dicts.

**Inputs/outputs:**
- `retrieve`: query, top_k, max_distance; outputs `[{id, source, page, section, text, distance}]`.

**Callers:** `graph_lc/nodes.py` (retrieve_node).

**Edge cases / errors:** Chroma returns L2 distance; lower = better. Postprocess filters by max_distance and limits per page.

---

## agent/app/reasoning.py

**Purpose:** Session summary computation, JSON schema validation, layer extraction for evidence. No LLM calls.

**Key classes/functions:**
- `ReasoningService` — `compute_session_summary`, `_detect_limitations`, `_object_has_geometry`, `extract_layers_used`, `validate_json_schema`.
- `KNOWN_LAYERS` — Set of layer names (Highway, Plot Boundary, Walls, etc.).

**Inputs/outputs:**
- `compute_session_summary(session_objects)`: outputs `SessionSummary` (layer_counts, plot_boundary_present, highways_present, total_objects, limitations).
- `_object_has_geometry(obj)`: checks `geometry.coordinates` or top-level `coordinates`.
- `extract_layers_used(session_objects, question)`: returns (layers_used, indices_used) based on keyword matching.
- `validate_json_schema`: returns list of warning strings.

**Callers:** `graph_lc/nodes.py` (validate_node, summarize_node, finalize_node).

**Edge cases / errors:** Empty session returns SessionSummary with limitations. Handles both "layer" and "Layer" keys.

**Potential refactors:** `extract_layers_used` used for evidence extraction; agent does not currently return evidence. Keyword mapping hardcoded.

---

## agent/app/routing.py

**Purpose:** Keyword-based routing: DOC_ONLY, JSON_ONLY, HYBRID. No LLM.

**Key functions:**
- `is_definition_only_question(question)` — Definition prefixes/patterns; excludes _DRAWING_INTENT_KEYWORDS.
- `is_json_only_question(question)` — Count/list prefixes/patterns; excludes definition-style.
- `get_query_mode(question)` — Returns "doc_only" | "json_only" | "hybrid". Order: doc_only checked first, then json_only.

**Inputs/outputs:**
- Input: normalized question (strip, lower).
- Output: QueryMode string.

**Callers:** `graph_lc/nodes.py` (route_node).

**Edge cases / errors:** Empty or non-string returns "hybrid". Object property questions (width/height/area) routed to json_only.

---

## agent/app/smalltalk.py

**Purpose:** Detects short greetings/pleasantries. Returns fixed response without RAG/LLM.

**Key functions:**
- `is_smalltalk(message)` — Max 4 words; no domain keywords; phrase in SMALLTALK_PHRASES.
- `get_smalltalk_response(message)` — Returns THANKS_RESPONSE or SMALLTALK_RESPONSE based on phrase.

**Constants:** DOMAIN_KEYWORDS, SMALLTALK_MAX_WORDS, SMALLTALK_PHRASES, THANKS_PHRASES.

**Inputs/outputs:**
- `is_smalltalk`: str; bool.
- `get_smalltalk_response`: str; response string.

**Callers:** `graph_lc/nodes.py` (smalltalk_node, finalize_node).

**Edge cases / errors:** Trailing punctuation stripped. Domain keywords block smalltalk (e.g. "hi property" → False).

---

## agent/app/guards/geometry_guard.py

**Purpose:** Deterministic guard for spatial questions when required layers exist but all objects lack geometry. Prevents LLM hallucination.

**Key functions:**
- `should_trigger_geometry_guard(question)` — True if question about this drawing + spatial keywords + not general-rule phrasing.
- `required_layers_for_question(question)` — Highway, Plot Boundary for fronting; adds Walls/Doors for elevation/wall/door.
- `has_geometry(obj)` — Checks geometry.coordinates non-empty.
- `missing_geometry_layers(session_objects, required_layers)` — Layers that have objects but all lack geometry.

**Inputs/outputs:**
- Input: question, session_objects.
- Output: list of layer names missing geometry.

**Callers:** `graph_lc/nodes.py` (geometry_guard_node), `followups.py` (missing_geometry_layers, has_geometry; imports from `guards.geometry_guard`).

**Edge cases / errors:** Layers with no objects not reported. Case-insensitive layer matching.

---

## agent/app/guards/doc_only_guard.py

**Purpose:** For DOC_ONLY questions, only use retrieved chunks (and call LLM) if the asked definition term appears in chunks. Prevents invented definitions. Term matching normalizes smart/curly quotes and hyphenation.

**Key functions:**
- `extract_definition_term(question)` — Regex extraction for "what is meant by X", "definition of X", etc.; returns normalized term (quotes stripped, hyphens as space).
- `term_appears_in_chunks(term, chunks)` — Normalized substring match (chunk text normalized the same way).
- `should_use_retrieved_for_doc_only(question, retrieved_chunks)` — False if term not in chunks; True if no term or term found.

**Inputs/outputs:**
- `should_use_retrieved_for_doc_only`: question, chunks; bool.

**Callers:** `rag/orchestrator.py` (stream_answer_ndjson), `graph_lc/nodes.py` (llm_node).

**Edge cases / errors:** No term extracted → allow LLM. Empty chunks → False.

---

## agent/app/followups.py

**Purpose:** Handles "what's needed?"-style follow-ups after geometry guard. Returns checklist without retrieval/LLM.

**Key functions:**
- `is_needs_input_followup(question)` — Regex match for English/Turkish phrases (e.g. "what do you need", "ne lazım").
- `get_missing_geometry_layers(session_objects)` — Uses geometry_guard logic.
- `build_needs_input_message(missing_layers)` — Checklist string.

**Inputs/outputs:**
- `is_needs_input_followup`: str; bool.
- `build_needs_input_message`: list of layer names; formatted message.

**Callers:** `graph_lc/nodes.py` (followup_node, finalize_node). Imports `missing_geometry_layers`, `has_geometry` from `guards.geometry_guard`.

**Edge cases / errors:** None.

---

## agent/app/rag/prompts.py

**Purpose:** Single source of truth for RAG prompt content (strings only; no LangChain at import time). SYSTEM_PROMPT, human template strings (HYBRID_HUMAN_TEMPLATE, DOC_ONLY_HUMAN_TEMPLATE), chunk formatting, and helpers for building full user prompt strings.

**Key symbols/functions:**
- `SYSTEM_PROMPT` — System message string.
- `format_chunk_for_prompt`, `format_chunk` (alias), `format_retrieved_chunks` — Chunk formatting.
- `build_user_prompt`, `build_user_prompt_doc_only` — Build full user prompt string (used by tests).

**Inputs/outputs:**
- `build_user_prompt`: question, json_objects, session_summary, retrieved_chunks; string.
- `build_user_prompt_doc_only`: question, retrieved_chunks; string.

**Callers:** `rag/chains.py` (builds ChatPromptTemplates from these strings), `agent/tests/test_prompts.py`.

**Edge cases / errors:** Empty chunks → "No relevant excerpts found.". None page/section handled.

---

## agent/app/rag/chains.py

**Purpose:** LCEL chains: doc_only_chain, hybrid_chain. Builds ChatPromptTemplate from rag/prompts strings; sync invoke and async stream helpers.

**Key symbols/functions:**
- `HYBRID_PROMPT`, `DOC_ONLY_PROMPT` — ChatPromptTemplate (built from SYSTEM_PROMPT + human templates in prompts.py).
- `build_chains(model, api_key, temperature, max_tokens)` — Creates ChatOpenAI; chains DOC_ONLY_PROMPT | llm | StrOutputParser and HYBRID_PROMPT | llm | StrOutputParser.
- `invoke_doc_only`, `invoke_hybrid` — Sync invoke.
- `astream_doc_only`, `astream_hybrid` — Async generators yielding tokens.
- `DOC_ONLY_EMPTY_MESSAGE` — "No explicit definition was found in the retrieved documents."

**Inputs/outputs:**
- `invoke_doc_only`: question, retrieved_chunks; answer string.
- `invoke_hybrid`: question, json_objects, session_summary, retrieved_chunks; answer string.

**Callers:** `main.py` (build_chains at startup), `graph_lc/nodes.py` (llm_node: invoke_doc_only, invoke_hybrid, DOC_ONLY_EMPTY_MESSAGE), `rag/orchestrator.py` (stream_answer_ndjson: astream_*, DOC_ONLY_EMPTY_MESSAGE).

**Edge cases / errors:** Empty chunks formatted as DOC_ONLY_EMPTY_MESSAGE for doc_only. Chains must be built before invoke.

---

## agent/app/rag/orchestrator.py

**Purpose:** Answer orchestration: sync run and NDJSON stream. Keeps endpoint logic out of main.py.

**Key functions:**
- `run_answer(request, answer_graph)` — Invokes compiled graph; returns AnswerResponse.
- `stream_answer_ndjson(request, reasoning_service, settings)` — Async generator: run_graph_until_route; if guard, finalize and emit; else stream doc_only or hybrid chain via astream_*; emit chunks + done. On exception yields `{"t":"error","message":...}`.

**Inputs/outputs:**
- `run_answer`: AnswerRequest, compiled StateGraph; AnswerResponse.
- `stream_answer_ndjson`: request, reasoning_service, settings; yields NDJSON lines.

**Callers:** `main.py` (/answer calls run_answer; /answer/stream uses stream_answer_ndjson).

**Edge cases / errors:** Guard path emits chunk + done; main path streams then done. Exception yields error line.

---

## agent/app/rag/__init__.py

**Purpose:** RAG package exports. Eager imports only for non–LangChain code (prompts, retrieval_postprocess) so tests can import prompts/postprocess without LangChain. LangChain-dependent symbols (build_chains, retrieve, run_answer, stream_answer_ndjson, HYBRID_PROMPT, DOC_ONLY_PROMPT, etc.) are lazy-loaded via `__getattr__`.

**Callers:** `main.py` (build_chains, run_answer, stream_answer_ndjson), tests.

---

## agent/app/graph_lc/__init__.py

**Purpose:** Exports GraphState, build_answer_graph, run_graph_until_route.

**Callers:** `main.py`.

---

## agent/app/graph_lc/state.py

**Purpose:** TypedDict for LangGraph state.

**Key symbols:**
- `GraphState` — question, session_objects, session_summary, doc_only, query_mode, retrieved_docs, answer_text, guard_result. total=False.
- `QueryMode` — Literal["doc_only", "json_only", "hybrid"].

**Callers:** `graph_builder.py`, `nodes.py`.

---

## agent/app/graph_lc/graph_builder.py

**Purpose:** Builds and compiles LangGraph StateGraph for hybrid RAG. Defines nodes and edges.

**Key functions:**
- `build_answer_graph(reasoning_service, settings)` — Adds nodes: validate, smalltalk, geometry_guard, followup, summarize, route, retrieve, llm, finalize. Conditional edges: smalltalk→finalize if guard; followup→finalize if missing_geometry/needs_input; else followup→summarize. Compiles with checkpointer=None.
- `run_graph_until_route(request, reasoning_service, settings)` — Runs nodes validate through retrieve; returns state dict (no llm/finalize). Used by streaming.

**Inputs/outputs:**
- `build_answer_graph`: outputs compiled StateGraph.
- `run_graph_until_route`: initial_state; outputs state with retrieved_docs, route, etc.

**Callers:** `main.py`.

**Edge cases / errors:** Each node wrapper injects reasoning_service and settings into state. Guard results short-circuit to finalize.

---

## agent/app/graph_lc/nodes.py

**Purpose:** Node implementations for LangGraph workflow.

**Key functions:**
- `validate_node` — Logs JSON schema warnings.
- `smalltalk_node` — Sets guard_result if smalltalk.
- `geometry_guard_node` — Sets guard_result if spatial + missing geometry.
- `followup_node` — Sets guard_result if needs_input + missing layers.
- `summarize_node` — Computes session_summary via reasoning_service.
- `route_node` — Sets query_mode, doc_only via routing.
- `retrieve_node` — Calls rag.retrieval.retrieve; skips for json_only.
- `llm_node` — Invokes doc_only or hybrid chain (rag.chains); doc_only guard (guards.doc_only_guard) applied.
- `finalize_node` — For guard paths: sets answer_text, session_summary. Smalltalk/missing_geometry/needs_input messages.

**Inputs/outputs:**
- Each returns dict updates for state.

**Callers:** `graph_builder.py` (wrappers).

**Edge cases / errors:** JSON_ONLY skips retrieval. Doc-only guard: returns DOC_ONLY_EMPTY_MESSAGE when term not in chunks. Lazy import of rag.retrieval, rag.chains, guards.doc_only_guard inside nodes to avoid circular imports.

---

## agent/app/models.py

**Purpose:** Pydantic models for agent API.

**Key classes:**
- `SessionSummary`, `AnswerRequest`, `AnswerResponse`, `IngestRequest`, `IngestResponse`, `DocumentInfo`, `SyncStatusResponse`, `HealthResponse`.
- `AnswerResponse`: answer, query_mode, session_summary. **No evidence field.**

**Inputs/outputs:**
- `AnswerRequest`: question, session_objects.
- `AnswerResponse`: answer, query_mode, session_summary.

**Callers:** `main.py`, `graph_lc/state.py` (SessionSummary).

**Edge cases / errors:** Backend expects evidence in QAResponse; agent omits it (see Doc vs Code Mismatches).

---

## agent/app/main.py

**Purpose:** FastAPI application entry (thin controllers). Lifespan: init vector_store, ingest.ingestion (PDFIngestionService), reasoning, document_registry, sync_service, build chains (rag.build_chains), build graph (graph_lc.build_answer_graph), run sync. Endpoints: /health, /sync/status, /ingest, /answer, /answer/stream.

**Key functions:**
- `/answer` — Calls rag.run_answer(request, answer_graph); returns AnswerResponse.
- `/answer/stream` — Returns StreamingResponse(rag.stream_answer_ndjson(request, reasoning_service, settings)).
- `_llm_available()` — Checks OPENAI_API_KEY set.

**Inputs/outputs:**
- `/answer`: AnswerRequest; AnswerResponse (answer, query_mode, session_summary).
- `/answer/stream`: AnswerRequest; NDJSON stream.
- `/ingest`: IngestRequest (force_reingest, delete_missing, source_id); IngestResponse.

**Callers:** Uvicorn. Callees: config, models, ingest.ingestion, vector_store, reasoning, document_registry, sync_service, graph_lc (build_answer_graph), rag (build_chains, run_answer, stream_answer_ndjson).

**Edge cases / errors:** 503 if services not initialized or LLM not configured. Orchestration (including guard path and streaming) lives in rag/orchestrator.py. Incremental sync on startup; delete_missing=False by default.

**Potential refactors:** Evidence not returned; backend QAResponse expects it. Consider adding evidence construction in finalize_node/AnswerResponse.
