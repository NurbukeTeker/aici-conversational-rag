# AICI Challenge – Compliance Checklist

This document maps the **AICI Conversational Q&A System** challenge requirements to the current implementation and flags any gaps.

---

## 1. Web Frontend

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Suggested: React or Vue.js | ✅ | React (Vite) |
| Interface for submitting natural-language questions | ✅ | Dashboard Q&A panel with input + "Ask" button |
| Input area for providing/updating JSON object list | ✅ | Textarea in "Drawing Objects (JSON)" panel with validation |
| Display answers from AI Agent | ✅ | Q&A messages with answer + evidence (document chunks, layers used) |
| Minimal styling; focus on usability | ✅ | App.css / index.css, theme (light/dark), clear layout |

**Notes:** All core frontend deliverables are met. Optional: consider using or removing the empty `SourcesPanel.jsx` (e.g. to show evidence sources) for clearer UX.

---

## 2. Backend API

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Suggested: FastAPI or Express.js | ✅ | FastAPI |
| User management with authentication (JWT) | ✅ | Register, login, `/auth/me`, JWT creation/validation |
| Session management for ephemeral object lists | ✅ | Redis: `session:{user_id}:objects` (and meta), TTL; PUT/GET `/session/objects` |
| Communication with AI Agent service | ✅ | Backend calls `POST {AGENT_URL}/answer` with question + session_objects |
| Support for frontend: submit queries, update object lists, authenticate | ✅ | `/qa`, `/session/objects`, `/auth/*` used by frontend |

**Notes:** Backend fully supports the required flows. Session state is per-user and sent to the Agent on each query.

---

## 3. AI Agent Service

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Suggested: LangChain, LangGraph | ⚠️ | Custom pipeline (vector_store, ingestion, prompts, llm_service). LangChain/LangGraph not used. |
| Hybrid RAG: persistent text + session JSON | ✅ | ChromaDB retrieval + session_objects in same request; single prompt combines both |
| Reasoning over both sources | ✅ | `prompts.py` system/user prompts; LLM receives question + retrieved chunks + full JSON + session summary |
| API endpoint for backend; return responses | ✅ | `POST /answer` (AnswerRequest → AnswerResponse with answer, evidence, session_summary) |
| Any suitable LLM | ✅ | OpenAI (gpt-4o) via `llm_service.py` |

**Notes:** The spec says “suggested” frameworks; the custom agent satisfies the functional requirements. If the evaluation strongly expects LangChain/LangGraph, consider adding a thin LangChain/LangGraph wrapper around the existing pipeline or documenting the choice.

---

## 4. Containerization & Documentation

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Dockerfile for backend and AI Agent | ✅ | `backend/Dockerfile`, `agent/Dockerfile`; frontend also has Dockerfile |
| Instructions to build and run locally | ✅ | README: clone, cp env.example .env, docker-compose up; also “Running Locally (without Docker)” |
| Steps to test queries and update object lists | ✅ | README “Example Queries”, “Demo Script”, SYSTEM_OVERVIEW verification script |
| Overview of architecture and design decisions | ✅ | README “Architecture”, “Design Decisions”; docs/ARCHITECTURE.md; SYSTEM_OVERVIEW.md |

**Notes:** All submission deliverables for containerization and documentation are covered.

---

## 5. Implementation Details

### 5.1 Ephemeral Object Handling

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Object list is session-specific; may change between queries | ✅ | Stored per user in Redis; fetched on each `/qa` |
| JSON format | ✅ | Request/response use JSON; backend validates DrawingObject schema |
| Always use most current version when generating answers | ✅ | Backend loads session objects from Redis immediately before calling Agent |
| Ephemeral objects NOT in vector database; in-memory for session | ✅ | Objects in Redis only; ChromaDB holds only document chunks |
| Users can add, remove, or update objects between queries | ✅ | Frontend textarea + “Update Session” (PUT `/session/objects`) |

**Notes:** Fully aligned with the spec. Redis is used as the session store (session-scoped, TTL); this satisfies “in-memory for the duration of the session” in a deployable way.

### 5.2 Persistent Text Embeddings

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Documents pre-embedded in vector DB (e.g. ChromaDB) | ✅ | ChromaDB; ingestion on startup + optional `/ingest` |
| Similarity search for each query | ✅ | `vector_store.search(query, top_k)` in agent |
| Embeddings fixed and unchanged during session | ✅ | No writes to vector store during Q&A; only read (search) |

**Notes:** Compliant.

### 5.3 Hybrid RAG Logic

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Responses derived from retrieved text + ephemeral object list | ✅ | Single LLM call with both in the user prompt |
| LLM receives both sources in one reasoning step | ✅ | `build_user_prompt()`: question + JSON + session summary + retrieved chunks |
| Example operations: count objects, analyze properties, cross-reference with rules | ✅ | Session summary (layer counts, flags); LLM instructed to use excerpts + JSON |

**Notes:** Compliant.

### 5.4 Backend Service (detailed)

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| User authentication (e.g. JWT login/registration) | ✅ | Register, login, JWT, protected routes |
| Session management for ephemeral object list per user | ✅ | Redis keys per user_id; GET/PUT session objects |
| Connection to Agent so queries use appropriate session state | ✅ | Backend gets session objects, then POST to Agent with question + session_objects |
| Real-time communication with Agent | ⚠️ | REST request/response only; no WebSockets or streaming |

**Notes:** “Real-time” in the spec may mean either (a) “each query uses current session state” (done) or (b) “WebSockets/streaming”. Current design is (a). If evaluators expect (b), consider adding streaming for the Agent response or documenting the choice.

### 5.5 Prompt Construction

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| System prompts to define agent behaviour and context | ✅ | `prompts.py` SYSTEM_PROMPT (rules for documents vs JSON, citations, etc.) |
| Query prompts include: user question, retrieved text, current object list | ✅ | `build_user_prompt()`: question, json_objects_pretty, session summary, retrieved_chunks_formatted |

**Notes:** Compliant.

---

## 6. Evaluation Criteria (self-check)

| Criterion | Status |
|-----------|--------|
| Agent answers accurately from both persistent embeddings and session object list, reflecting updates between queries | ✅ Designed for this; multi-user demo in README |
| Hybrid RAG integrates persistent text and ephemeral session data; retrieval and prompt construction correct | ✅ |
| End-to-end behaviour: frontend (queries + object list), backend (auth + sessions), Agent (synthesis) | ✅ |
| Codebase well-structured, readable, maintainable; clear separation of concerns | ✅ (frontend / backend / agent) |
| Error handling and robustness (invalid object lists, malformed queries) | ✅ Validation (e.g. DrawingObject, session limits), structured error responses |

---

## 7. Optional / Plus Features

| Feature | Status | Notes |
|---------|--------|--------|
| Advanced PDF preprocessing (e.g. text + images separately) | ❌ | Basic pypdf text extraction only |
| Agentic AI (planning, verification, autonomous behaviour) | ❌ | Single-step RAG; no multi-step agent loop |
| Verification of object lists against text embeddings | ⚠️ | Session summary and schema validation; no explicit “compliance check” vs rules |

**Notes:** These are optional; the core challenge is met without them.

---

## 8. Summary and Recommended Actions

- **Core deliverables:** All main requirements (frontend, backend, agent, containerization, documentation, ephemeral handling, persistent embeddings, hybrid RAG, prompts) are satisfied.
- **Suggested before submission:**
  1. **Real-time wording:** If “real-time communication” is interpreted as WebSockets/streaming, add a short note in README or ARCHITECTURE that the design uses REST with “current session state per request” and why (simplicity, challenge scope).
  2. **Agent framework:** If evaluators expect LangChain/LangGraph, either integrate a minimal LangChain/LangGraph layer or add a sentence in the docs that the agent is a custom pipeline meeting the same functional requirements.
  3. **Frontend:** Either implement a simple Sources Panel (e.g. evidence/sources) or remove the empty `SourcesPanel.jsx` and any references so the repo doesn’t imply unfinished features.
  4. **Docs vs code:** Update README and SYSTEM_OVERVIEW so “user storage” is described as SQLite (persistent), not in-memory, to avoid confusion.

After these small clarifications and tidy-ups, the submission is aligned with the AICI challenge specification and evaluation criteria.
