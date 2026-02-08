# AICI Conversational RAG — System Overview (Deep)

Interview-grade technical documentation of the entire codebase. All claims are grounded in verified code paths.

---

## 1. Executive Summary

The **AICI Hybrid RAG** system answers planning-regulation questions by combining two knowledge sources: (1) **persistent PDF embeddings** in ChromaDB, and (2) **ephemeral session JSON** (drawing objects) stored in Redis. The Agent is stateless and receives `question` + `session_objects` on every request; the Backend owns auth, session, and orchestration. Three services comprise the runtime: **Frontend** (React/Vite), **Backend** (FastAPI), and **Agent** (FastAPI + LangChain/LangGraph). PDF ingestion runs on agent startup and via `/ingest`; ChromaDB uses content hashing for incremental sync. Routing is keyword-based: DOC_ONLY (definition-style), JSON_ONLY (count/list layers), or HYBRID. Guards handle smalltalk, missing geometry, and doc-only absence without calling the LLM.

---

## 2. System Architecture

### 2.1 ASCII Diagram

```
                              ┌──────────────────────────────────────────────────────────┐
                              │                     DOCKER NETWORK                         │
                              │                                                           │
   ┌─────────────┐           │   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
   │  Browser    │  :3000    │   │  Frontend   │────▶│  Backend    │────▶│   Agent     │  │
   │  (User)     │──────────▶│   │  (nginx)    │     │  (FastAPI)  │     │  (FastAPI)  │  │
   └─────────────┘           │   │  port 80    │     │  port 8000  │     │  port 8001  │  │
                              │   └─────────────┘     └──────┬──────┘     └──────┬──────┘  │
                              │          │                    │                   │        │
                              │          │ proxy /api         │                   │        │
                              │          ▼                    ▼                   ▼        │
                              │   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
                              │   │             │     │   Redis     │     │  ChromaDB   │  │
                              │   │             │     │   :6379     │     │  /data/chroma│  │
                              │   │             │     │  (session)  │     │  (vectors)  │  │
                              │   │             │     └─────────────┘     └─────────────┘  │
                              │   │             │     ┌─────────────┐     ┌─────────────┐  │
                              │   │             │     │  SQLite     │     │  Document   │  │
                              │   │             │     │ users.db    │     │  Registry   │  │
                              │   │             │     │  (auth)     │     │  (hashes)   │  │
                              │   │             │     └─────────────┘     └─────────────┘  │
                              └──────────────────────────────────────────────────────────┘
```

### 2.2 Ports and Base URLs

| Service | Port (host) | Internal URL | Env Var |
|---------|-------------|--------------|---------|
| Frontend | 3000 | http://localhost:3000 | — |
| Backend | 8000 | http://backend:8000 | `AGENT_SERVICE_URL` |
| Agent | 8001 | http://agent:8001 | — |
| Redis | 6379 | redis:6379 | `REDIS_HOST`, `REDIS_PORT` |

- Frontend dev: `vite.config.js` proxies `/api` → `http://localhost:8000`.
- Production: `nginx.conf` proxies `/api` → `http://backend:8000`.
- Backend calls Agent via `AGENT_SERVICE_URL` (default `http://agent:8001`).

### 2.3 Docker Compose Topology

**File:** `docker-compose.yml`

- **redis:** Standalone, no `depends_on`. Volumes: `redis_data`.
- **agent:** Depends on nothing. Volumes: `./data:/data`, `chroma_data:/data/chroma`. Env: `OPENAI_API_KEY`, `CHROMA_PERSIST_DIRECTORY`, `PDF_DATA_DIRECTORY`.
- **backend:** `depends_on: redis, agent` (with health conditions). Volumes: `./data:/data`. Env: `JWT_SECRET_KEY`, `REDIS_HOST`, `AGENT_SERVICE_URL`, `DATABASE_URL`.
- **frontend:** `depends_on: backend`. Proxies `/api` to backend.

**Startup order:** redis → agent (health) → backend (health) → frontend.

---

## 3. End-to-End Flows

### 3.A Register → Login → JWT Issuance

| Step | Endpoint | Request | Response | Code Path |
|------|----------|---------|----------|-----------|
| 1 | `POST /auth/register` | `{username, email, password}` | `UserResponse` (201) | `backend/app/main.py:register()` → `user_service.create_user()` |
| 2 | `POST /auth/login` | form-urlencoded `username`, `password` | `{access_token, expires_in}` | `backend/app/main.py:login()` → `user_service.authenticate()` → `auth.create_access_token()` |

**Code paths:**
- Register: `backend/app/main.py:211-255` → `backend/app/user_service.py:create_user()`; password hashed via `auth.get_password_hash()` (Argon2).
- Login: `backend/app/main.py:258-286` → `backend/app/user_service.py:authenticate()` → `backend/app/auth.py:create_access_token()`.
- JWT payload: `{"sub": username, "user_id": user.id, "exp": ...}`. Algorithm: HS256.

### 3.B Update Session JSON → Redis Storage → TTL Refresh

| Step | Endpoint | Request | Response | Code Path |
|------|----------|---------|----------|-----------|
| 1 | `PUT /session/objects` | `{objects: [...]}` | `SessionObjectsResponse` | `backend/app/main.py:update_session_objects()` |
| 2 | — | — | Redis `SET` with TTL | `backend/app/session.py:set_objects()` |

**Redis keys:** `session:{user_id}:objects`, `session:{user_id}:meta`. TTL: `session_ttl_seconds` (default 3600). TTL is set on each `set_objects()` call (refresh on update).

### 3.C Ask Question (REST) → Backend → Agent → RAG → Answer

| Step | Component | Action | Code Path |
|------|-----------|--------|-----------|
| 1 | Frontend | `POST /api/qa` with `{question}` | `frontend/src/services/api.js:qaApi.ask()` |
| 2 | Backend | Load session from Redis, POST to Agent | `backend/app/main.py:ask_question()` → `session_service.get_objects()` → `httpx.post(agent/answer)` |
| 3 | Agent | Run LangGraph workflow | `agent/app/main.py:answer_question()` → `rag.orchestrator.run_answer()` → `answer_graph.invoke()` |
| 4 | Agent | Validate → smalltalk → geometry_guard → followup → summarize → route → retrieve → llm → finalize | `agent/app/graph_lc/graph_builder.py`, `agent/app/graph_lc/nodes.py` |
| 5 | Backend | Return `QAResponse(**agent_response)` | `backend/app/main.py:529` |

**Request shape (backend → agent):** `{question: str, session_objects: list[dict]}`.  
**Response shape (agent):** `{answer, query_mode, session_summary}`. See §11 for evidence mismatch.

### 3.D Streaming (WebSocket + NDJSON)

| Step | Component | Action | Code Path |
|------|-----------|--------|-----------|
| 1 | Frontend | Connect `ws://host/api/ws/qa`, then send `{type:"auth",token:"<jwt>"}` as first message | `frontend/src/pages/Dashboard.jsx:getWsQaUrl()` + onopen |
| 2 | Backend | Accept WS, require first message auth; decode JWT, then forward to Agent stream | `backend/app/main.py:websocket_qa()` |
| 3 | Backend | `httpx.stream(POST agent/answer/stream)` | `backend/app/main.py:447-458` |
| 4 | Backend | For each NDJSON line from Agent, `websocket.send_json(obj)` | `backend/app/main.py:459-466` |
| 5 | Agent | `run_graph_until_route()` + `astream_doc_only` / `astream_hybrid` | `agent/app/rag/orchestrator.py:stream_answer_ndjson()` (called from main.py) |
| 6 | Frontend | Append `data.c` for `t:chunk`; finalize on `t:done` | `frontend/src/pages/Dashboard.jsx:257-305` |

**NDJSON format:** `{"t":"chunk","c":"..."}` then `{"t":"done","answer":"...","query_mode":"...","session_summary":{...}}`.

### 3.E PDF Ingestion

| Step | Trigger | Action | Code Path |
|------|---------|--------|-----------|
| 1 | Agent startup | `sync_service.sync(delete_missing=False)` | `agent/app/main.py:78-93` |
| 2 | `POST /ingest` | `sync_service.sync()` or `force_reingest()` | `agent/app/main.py:161-191` |
| 3 | Sync | For each PDF: hash → status (NEW/UNCHANGED/UPDATED) | `agent/app/sync_service.py:_process_document()` |
| 4 | Ingestion | `pypdf` extract → `RecursiveCharacterTextSplitter` (1000/200) | `agent/app/ingest/ingestion.py` |
| 5 | Storage | Chunks + metadata → ChromaDB via `VectorStoreService` | `agent/app/vector_store.py:add_documents()` |
| 6 | Registry | `DocumentRegistry.register(source_id, hash, chunk_ids)` | `agent/app/document_registry.py` |

**PDF location:** `data/pdfs/` (Docker: `/data/pdfs`). **Chroma persist:** `CHROMA_PERSIST_DIRECTORY` → `/data/chroma`. **Registry:** `{chroma_dir}/document_registry.json`.

---

## 4. Backend Deep Dive (FastAPI)

### 4.1 Folder Map: `backend/app/`

| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app, routes, exception handlers, lifespan |
| `auth.py` | JWT create/decode, OAuth2PasswordBearer, Argon2 hashing |
| `session.py` | Redis SessionService, keys `session:{user_id}:objects|meta` |
| `database.py` | SQLAlchemy engine, User model, `get_db_session` |
| `user_service.py` | User CRUD, validation, authenticate |
| `models.py` | Pydantic request/response models |
| `config.py` | Pydantic Settings from env |
| `validators.py` | Password, username, email validators |
| `export_service.py` | Excel/JSON export of dialogues |

### 4.2 Endpoints by Router (All in `main.py`)

| Endpoint | Auth | Method | Description |
|----------|------|--------|-------------|
| `/auth/register` | No | POST | Create user |
| `/auth/login` | No | POST | Return JWT |
| `/auth/me` | Bearer | GET | Current user info |
| `/auth/check-username` | No | GET | Username availability |
| `/auth/check-email` | No | GET | Email availability |
| `/auth/check-password` | No | POST | Password strength |
| `/session/objects` | Bearer | PUT, GET | Update/get session JSON |
| `/qa` | Bearer | POST | Ask question (REST) |
| `/ws/qa` | First-message auth | WS | Streaming Q&A |
| `/health` | No | GET | Redis + agent status |
| `/export/excel` | Bearer | POST | Download Excel |
| `/export/json` | Bearer | POST | Download JSON |

### 4.3 Session Model (Redis)

- **Key format:** `session:{user_id}:objects`, `session:{user_id}:meta`.
- **TTL:** `session_ttl_seconds` (3600). Set on every `set_objects()`.
- **Serialization:** JSON for `objects`; `meta` = `{updated_at, object_count}`.

### 4.4 Auth Model

- **Hashing:** Argon2 via `passlib.CryptContext(schemes=["argon2"])` — `backend/app/auth.py:17`.
- **JWT:** HS256, claims `sub` (username), `user_id`, `exp`. Created in `auth.create_access_token()`.
- **User DB:** SQLite, `users` table — `backend/app/database.py:User`. Fields: id, username, email, hashed_password, display_name, is_active, is_verified, created_at, updated_at, last_login_at.

### 4.5 Error Handling

- `RequestValidationError` → 422 with field details + example payload — `backend/app/main.py:validation_exception_handler`.
- `json.JSONDecodeError` → 400 — `backend/app/main.py:json_decode_exception_handler`.
- Request size > 512 KB → 413 — `RequestSizeLimitMiddleware`.

---

## 5. Agent Deep Dive (FastAPI + LangChain/LangGraph)

For file-by-file agent documentation, see [docs/AGENT_CODE_GUIDE.md](AGENT_CODE_GUIDE.md).

### 5.1 Folder Map: `agent/app/`

| Path | Responsibility |
|------|----------------|
| `main.py` | FastAPI app (thin controllers): `/answer`, `/answer/stream`, `/ingest`, `/health`, `/sync/status`. Delegates to `rag.orchestrator`. |
| `graph_lc/graph_builder.py` | LangGraph StateGraph construction |
| `graph_lc/nodes.py` | Node implementations (validate, smalltalk, geometry_guard, followup, summarize, route, retrieve, llm, finalize) |
| `graph_lc/state.py` | GraphState TypedDict |
| `rag/orchestrator.py` | `run_answer()`, `stream_answer_ndjson()` — answer flow orchestration |
| `rag/prompts.py` | Prompt strings; format_chunk, build_user_prompt helpers |
| `rag/chains.py` | LCEL chains (doc_only, hybrid), invoke/astream; ChatPromptTemplate from prompts |
| `rag/retrieval.py` | LangChain Chroma retrieve(); uses retrieval_postprocess.postprocess |
| `rag/retrieval_postprocess.py` | postprocess(chunks) — distance filter, max per (source, page) |
| `ingest/ingestion.py` | PDF extraction, RecursiveCharacterTextSplitter |
| `guards/doc_only_guard.py` | Definition-term-in-chunks check |
| `guards/geometry_guard.py` | Missing-geometry detection |
| `routing.py` | DOC_ONLY / JSON_ONLY / HYBRID (keyword-based) |
| `vector_store.py` | ChromaDB add/search/delete (sync path) |
| `chroma_client.py` | Shared PersistentClient |
| `document_registry.py` | SHA256 hashing, DocumentRecord |
| `sync_service.py` | Incremental sync (NEW/UNCHANGED/UPDATED/DELETED) |
| `reasoning.py` | Session summary, validate JSON, extract layers |
| `smalltalk.py` | Greeting detection |
| `followups.py` | "What's needed?" checklist |

### 5.2 `/answer` and `/answer/stream` Call Graph

- **Sync:** `agent/app/main.py:answer_question()` → `rag.orchestrator.run_answer(request, answer_graph)` → `answer_graph.invoke(initial_state)`.
- **Stream:** `main.py` → `rag.orchestrator.stream_answer_ndjson()` → `run_graph_until_route()` (from `graph_lc/graph_builder.py`) → then `astream_doc_only` or `astream_hybrid` from `rag/chains.py` → `finalize_node` → NDJSON yield.

### 5.3 Routing Logic (DOC_ONLY / JSON_ONLY / HYBRID)

**Location:** `agent/app/routing.py:get_query_mode()`.

- **DOC_ONLY:** Definition-style prefixes (`what is`, `define`, etc.) and patterns; excludes `_DRAWING_INTENT_KEYWORDS`.
- **JSON_ONLY:** Count/list prefixes (`how many`, `list`, etc.) and patterns; excludes definition-style.
- **HYBRID:** Default when neither applies.

Decided in `route_node` → `routing.get_query_mode(question)`.

### 5.4 Retrieval

- **Chroma:** Shared client from `chroma_client.get_chroma_client()`, collection `planning_documents`.
- **Config:** `retrieval_top_k` (5), `retrieval_max_distance` (optional).
- **Postprocess:** `rag/retrieval_postprocess.py:postprocess()` — filter by distance, max 2 chunks per (source, page), sort by distance.

### 5.5 Prompting

- **System prompt:** `rag/prompts.py:SYSTEM_PROMPT` — docs authoritative, JSON ground truth, no hallucination, cite short phrases.
- **Doc-only:** Question + retrieved chunks.
- **Hybrid:** Question + JSON pretty + session summary (layer_counts, plot_boundary_present, highways_present, limitations) + retrieved chunks.
- **Session summary:** Computed in `summarize_node` via `reasoning_service.compute_session_summary()`.

### 5.6 Evidence (Agent)

The agent **does not** return structured evidence. `AnswerResponse` has `answer`, `query_mode`, `session_summary` only (`agent/app/models.py:25-31`). See §11 for mismatch with backend/frontend.

### 5.7 Guards

| Guard | Location | Condition | Return |
|-------|----------|-----------|--------|
| Smalltalk | `nodes.smalltalk_node` | `smalltalk.is_smalltalk(question)` | `guard_result: {type: "smalltalk"}` → `finalize_node` uses `smalltalk.get_smalltalk_response()` |
| Missing geometry | `nodes.geometry_guard_node` | Spatial question about this drawing + required layers lack geometry | Deterministic message with missing layers |
| Doc-only absence | `guards/doc_only_guard.py:should_use_retrieved_for_doc_only()` | Definition term not in chunks | `DOC_ONLY_EMPTY_MESSAGE` |
| Needs-input followup | `nodes.followup_node` | "What's needed?" + missing layers | Checklist message |

### 5.8 LangGraph State and Flow

**State schema:** `agent/app/graph_lc/state.py:GraphState` — `question`, `session_objects`, `session_summary`, `doc_only`, `query_mode`, `retrieved_docs`, `answer_text`, `guard_result`.

**Flow:** validate → smalltalk → (if guard) finalize → geometry_guard → followup → (if guard) finalize → summarize → route → retrieve → llm → finalize → END.

---

## 6. Frontend Deep Dive (React/Vite)

### 6.1 Folder Map: `frontend/src/`

| Path | Responsibility |
|------|----------------|
| `main.jsx` | React root, ThemeProvider, AuthProvider |
| `App.jsx` | Route: LoginPage or Dashboard based on auth |
| `pages/LoginPage.jsx` | Login/register, validation, authApi |
| `pages/Dashboard.jsx` | JSON editor, Q&A panel, WebSocket/REST, export |
| `context/AuthContext.jsx` | token/user in localStorage, login/logout |
| `context/ThemeContext.jsx` | theme (light/dark) in localStorage |
| `services/api.js` | fetch wrappers, JWT in Authorization header |
| `styles/` | App.css, index.css |

### 6.2 API Client

- **Base URL:** `/api` (relative; proxied to backend in dev/prod).
- **JWT:** Stored in `localStorage.token`, sent as `Authorization: Bearer <token>`.
- **Errors:** `ApiError` with `message` and `status`; `normalizeDetail()` for backend `detail` (string or array).

### 6.3 Streaming UI

- WebSocket: `ws://host/api/ws/qa`; first message `{type:"auth",token:"..."}`. On `t:chunk`, append `data.c` to `streamingAnswer`.
- Human-speed reveal: ~35 chars/sec via `setInterval` and `streamingDisplayLength` — `Dashboard.jsx:147-184`.
- Finalize on `t:done`; REST fallback streams full answer then shows it.

### 6.4 State Management and Theme

- **Auth:** React Context (`AuthContext`) + localStorage.
- **Theme:** `ThemeContext` + `localStorage.theme`; `data-theme` on document root.

### 6.5 Evidence UI

Dashboard does **not** render a dedicated Evidence section. It parses the answer text to strip evidence markers (`parseAnswerNarrative`) but does not display `evidence.document_chunks` or `evidence.session_objects`. CSS for `.qa-evidence` exists in `App.css` but is unused in the current Dashboard markup.

---

## 7. Data & Config

### 7.1 env.example → Service Mapping

| Env Var | Service | Usage |
|---------|---------|-------|
| `OPENAI_API_KEY` | Agent | LLM calls |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Backend | JWT creation/validation |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | Backend | Session storage |
| `DATABASE_URL` | Backend | SQLite users |
| `AGENT_SERVICE_URL` | Backend | Agent HTTP calls |
| `CHROMA_PERSIST_DIRECTORY` | Agent | Chroma persist path |
| `PDF_DATA_DIRECTORY` | Agent | PDF source directory |
| `BACKEND_URL` | — | Referenced in env.example; not used in code for service calls |

### 7.2 data/ Directory

- `data/pdfs/` — PDFs to ingest.
- `data/sample_objects.json` — Sample drawing objects.
- `data/users.db` — SQLite (when `DATABASE_URL` points here). Docker uses `sqlite:////data/users.db`.
- Chroma + registry live in `chroma_data` volume or `./data/chroma` when not using Docker.

### 7.3 Document Registry/Sync

- **File:** `{CHROMA_PERSIST_DIRECTORY}/document_registry.json`.
- **Hashing:** SHA256 of file contents — `document_registry.DocumentRegistry.compute_hash()`.
- **Status:** NEW, UNCHANGED, UPDATED, DELETED — `sync_service.DocumentSyncService.sync()`.

---

## 8. Observability & Testing

### 8.1 Logging

- Backend: `logging.basicConfig(INFO)`; logger in `main`, `session`, `auth`, `user_service`.
- Agent: Same pattern; log in nodes, sync, ingestion.

### 8.2 Tests

- **Backend:** `backend/tests/` — auth, models, session_objects, validators. Run: `cd backend && pytest -q`.
- **Agent:** `agent/tests/` — evidence_acceptance, followups, geometry_guard, graph, prompts, reasoning, retrieval, routing, smalltalk. Run: `cd agent && pytest -q`.
- **Frontend:** Build only in CI; no unit tests found.

### 8.3 Lint/Format

No explicit eslint/prettier or ruff config found in repo root. CI runs `pytest` and `npm run build`.

---

## 9. Security Notes

- **JWT:** HS256, `exp` claim, secret from `JWT_SECRET_KEY`. No refresh token.
- **Password:** Argon2 via passlib.
- **CORS:** `allow_origins=["*"]` — `backend/app/main.py:162`, `agent/app/main.py:111`.
- **Payload limit:** 512 KB — `RequestSizeLimitMiddleware`.
- **Object limit:** 1000 objects per session — `backend/app/models.py:MAX_OBJECTS_COUNT`.

---

## 10. Interview Cheat Sheet

### Technical Decisions & Tradeoffs

1. **Stateless Agent** — Session always supplied by backend; simplifies scaling and isolation.
2. **Redis for session** — TTL-based expiry; keys `session:{user_id}:objects|meta`.
3. **LangGraph** — Single StateGraph for all answer paths; guards short-circuit without LLM.
4. **Keyword routing** — No LLM for DOC_ONLY/JSON_ONLY; fast and deterministic.
5. **Doc-only guard** — Only answer when asked term appears in retrieved chunks; avoids invented definitions.
6. **Incremental ingestion** — SHA256 + registry; only changed PDFs re-ingested.
7. **Argon2** — Strong password hashing.
8. **Single-step reasoning** — One retrieval + one LLM call per question.
9. **Chroma L2 distance** — Lower = better; postprocess filters by distance and max per page.
10. **Streaming via NDJSON** — Backend proxies Agent stream; frontend uses WebSocket or REST.
11. **Shared Chroma client** — Ingestion and retrieval use same PersistentClient to avoid config mismatch.
12. **Session summary** — Reduces prompt size; preserves layer counts and flags.

### Known Limitations / Future Work

1. Agent does not return structured evidence; backend QAResponse expects it (see §11).
2. No refresh token; JWT expiry requires re-login.
3. CORS `*`; not suitable for strict production without narrowing origins.
4. No rate limiting on auth or QA endpoints.
5. Frontend does not display evidence UI.
6. No e2e tests across services.
7. SQLite for users; scale-out would need a different DB.
8. Export dialogue format expects evidence but frontend sends dialogues without it.

### Likely Interview Questions

1. **How does hybrid RAG work?** — Persistent docs in Chroma + ephemeral JSON in Redis; routing chooses doc_only/json_only/hybrid; single LLM call with combined context.
2. **When does retrieval run?** — For DOC_ONLY and HYBRID; skipped for JSON_ONLY.
3. **What triggers the geometry guard?** — Question about this drawing + spatial keywords + required layers (e.g. Highway, Plot Boundary) exist but all objects lack geometry.
4. **How is doc-only guarded?** — `should_use_retrieved_for_doc_only`: only use chunks if the asked definition term appears in retrieved text.
5. **Where is session summary computed?** — `reasoning_service.compute_session_summary()` in `summarize_node`.
6. **How does streaming work end-to-end?** — Frontend WS → backend → Agent `POST /answer/stream` (NDJSON) → backend forwards lines → frontend appends chunks.
7. **What is the Redis key format?** — `session:{user_id}:objects` and `session:{user_id}:meta`.
8. **How does incremental ingestion work?** — SHA256 per PDF; registry stores hash + chunk_ids; NEW/UNCHANGED/UPDATED/DELETED; only changed docs re-ingested.
9. **Where is routing decided?** — `routing.get_query_mode(question)` in `route_node`; keyword-based.
10. **What password hashing is used?** — Argon2 via passlib.

---

## 11. Doc vs Code Mismatches

| README Claim | What Code Actually Does | Recommended Doc Fix |
|--------------|-------------------------|---------------------|
| "Evidence (document chunks + session layers/indices) is returned with every answer" | Agent `AnswerResponse` has no `evidence` field; only `answer`, `query_mode`, `session_summary`. Backend `QAResponse` requires `evidence`. | Either implement evidence in Agent and return it, or make `evidence` optional in `QAResponse` and document that evidence is not yet returned. |
| "Evidence is shown… collapse by default for doc_only/hybrid" | Frontend Dashboard does not render evidence; no UI component consumes `evidence`. | Update README to state that evidence UI is not implemented, or implement evidence display. |
| "JSON_ONLY: The Evidence section is not rendered at all" | Frontend does not render Evidence for any mode. | Same as above. |
| "Retrieved vs used: only used chunks appear in evidence.document_chunks" | Agent does not return evidence; no used-vs-retrieved distinction in API. | Align docs with current behavior (no evidence returned). |
| "ChromaDB default sentence-transformer (e.g. all-MiniLM-L6-v2)" | Chroma client uses default embedding; `chroma_client.py` and `config.py` do not explicitly set embedding model. | Confirm actual Chroma default and document it, or make embedding config explicit. |

---

*Generated from codebase inspection. No application behavior was modified.*
