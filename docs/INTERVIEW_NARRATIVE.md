# Interview Narrative Pack

A speak-aloud script for presenting the AICI Hybrid RAG system. Every factual claim is verified in code.

---

## 1. 30-Second Pitch

*"AICI is a hybrid RAG system for planning and regulatory documents. It answers questions by combining two knowledge sources: persistent PDFs in a vector store and ephemeral drawing objects in per-user session state. Users get auditable answers grounded in their documents and their current drawing—without inventing rules or geometry. It's built for planners, developers, and evaluators who need trustworthy answers and clear evidence."*

**What it is:** Hybrid RAG (retrieval + session JSON).  
**Who it's for:** Planning practitioners, developers, evaluators.  
**Problem solved:** Combines regulatory text with drawing data; avoids hallucination via guards and doc-only filtering.  
**Why trustworthy:** Guards (smalltalk, missing geometry, doc-only absence) return deterministic responses without LLM calls when needed. Argon2 passwords, JWT auth, explicit routing.

---

## 2. 2-Minute Architecture Walkthrough

*"When a user asks a question, here's the path."*

**User action in UI:** User types a question in the Q&A panel. The frontend prefers WebSocket when connected—`frontend/src/pages/Dashboard.jsx:247`—otherwise falls back to REST.

**Frontend → Backend:**  
- WebSocket: connects to `/api/ws/qa?token=<jwt>`. Token in query; backend decodes JWT in `backend/app/main.py:434-441`.  
- REST: `POST /api/qa` with Bearer token. Backend loads session from Redis—`session_service.get_objects(user_id)` in `backend/app/main.py:510`—and forwards `{question, session_objects}` to the Agent.

**Backend → Agent:**  
- Agent receives question and session JSON on every request. Stateless: no session stored in the Agent.

**Agent flow:**  
1. LangGraph workflow: validate → smalltalk → geometry_guard → followup → summarize → route → retrieve → llm → finalize.  
2. **Routing** (`agent/app/routing.py:get_query_mode`): DOC_ONLY (definition-style), JSON_ONLY (count/list), or HYBRID (both).  
3. **Retrieval:** For DOC_ONLY and HYBRID, Chroma similarity search; skipped for JSON_ONLY.  
4. **LLM:** Single prompt with system instructions, question, retrieved chunks, and (for HYBRID) session JSON and summary.

**Stores:**
- **Redis:** Session objects, keys `session:{user_id}:objects` and `session:{user_id}:meta`. TTL 3600s, refreshed on update. `backend/app/session.py:28-33`.  
- **ChromaDB:** PDF embeddings at `CHROMA_PERSIST_DIRECTORY`; collection `planning_documents`. `agent/app/chroma_client.py:get_chroma_client()`.  
- **SQLite:** Users table for auth. `backend/app/database.py:User`.  
- **Document registry:** SHA256 hashes for incremental ingestion. `agent/app/document_registry.py`.

**Evidence:** The Agent returns `answer`, `query_mode`, `session_summary`—no structured evidence field. The README describes an evidence pipeline; the UI does not render evidence. See §7 Red Flags.

```
User → Frontend (React) → Backend (FastAPI) → Agent (FastAPI + LangGraph)
                              ↓                      ↓
                         Redis (session)        ChromaDB (vectors)
                         SQLite (users)         Document registry
```

---

## 3. 10-Minute Deep Dive Story

### A. Problem & Constraints

*"We needed to answer planning-regulation questions using both PDFs and per-session drawing objects. Constraints: the Agent must be stateless, session data ephemeral, and answers auditable. We avoid LLM calls when deterministic answers suffice."*

### B. Architecture & Separation of Concerns

*"Three services. Backend owns auth and session; it loads session from Redis and forwards it to the Agent on every request. Agent owns retrieval and LLM; it never stores user data. Frontend owns presentation and token handling. Clear boundaries."*

- Backend: `backend/app/main.py` — auth routes, session routes, QA orchestration, WebSocket proxy.  
- Agent: `agent/app/main.py` — `/answer`, `/answer/stream`, `/ingest`, `/health`.  
- Frontend: `frontend/src/pages/Dashboard.jsx` — JSON editor, Q&A panel, export.

### C. Data Flow (Persistent vs Ephemeral)

*"Persistent: PDFs in ChromaDB. Chunked with RecursiveCharacterTextSplitter, 1000 chars, 200 overlap—`agent/app/ingest/ingestion.py`. Metadata: source, page, chunk_id, optional section. Incremental sync via SHA256 in the document registry—`agent/app/sync_service.py`."*

*"Ephemeral: session objects in Redis. Keys `session:{user_id}:objects` and `session:{user_id}:meta`. TTL 3600s; refreshed on PUT. Never embedded. Sent in full (or summarized) in the HYBRID prompt."*

### D. Agent Routing (DOC_ONLY / JSON_ONLY / HYBRID) and Why

*"Routing is keyword-based, no LLM. `agent/app/routing.py:get_query_mode()`. DOC_ONLY: definition prefixes like 'what is', 'define'; excludes drawing-intent keywords. JSON_ONLY: count/list prefixes like 'how many', 'list the layers'; excludes definition-style. HYBRID: everything else."*

*"Why: DOC_ONLY avoids injecting session JSON when the user only wants a definition. JSON_ONLY skips retrieval—the answer comes from session JSON only. HYBRID combines both. Fast and deterministic."*

### E. Retrieval & Prompt Construction (How You Prevent Hallucinations)

*"Retrieval: top-k 5, optional max_distance filter. Postprocess: max 2 chunks per (source, page), sort by distance. `agent/app/rag/retrieval_postprocess.py:postprocess`; retrieval in `agent/app/rag/retrieval.py`."*

*"Doc-only guard: `agent/app/guards/doc_only_guard.py:should_use_retrieved_for_doc_only()`. For definition-style questions, we only call the LLM if the asked term appears in retrieved chunks. Otherwise we return 'No explicit definition was found in the retrieved documents.'—`agent/app/rag/chains.py:DOC_ONLY_EMPTY_MESSAGE`."*

*"Prompt: system prompt forbids inventing objects, measurements, or rules. Treats retrieved docs as authoritative and JSON as ground truth. `agent/app/rag/prompts.py:SYSTEM_PROMPT`."*

### F. Evidence Policy (Used vs Retrieved; What UI Shows)

*"Designed policy: only used chunks in evidence; retrieved-but-unused in debug when `include_debug: true`. JSON_ONLY: no document evidence. DOC_ONLY/HYBRID: document chunks + session layers."*

*"Current implementation: the Agent does not return structured evidence. `AnswerResponse` has `answer`, `query_mode`, `session_summary` only—`agent/app/models.py:25-31`. Backend `QAResponse` expects `evidence`—`backend/app/models.py:331`. The REST `/qa` path would fail on validation. WebSocket path works because it forwards raw NDJSON and does not construct QAResponse."*

*"Frontend: no Evidence section. `parseAnswerNarrative` strips evidence markers from answer text; `.qa-evidence` CSS exists but is unused. `frontend/src/pages/Dashboard.jsx`."*

### G. Streaming Path (If Implemented)

*"Implemented. Frontend connects WebSocket `/api/ws/qa?token=<jwt>`. Backend decodes token, accepts WS, streams POST to Agent `/answer/stream`. Agent uses `rag.orchestrator.stream_answer_ndjson()`: runs `run_graph_until_route`—`agent/app/graph_lc/graph_builder.py:run_graph_until_route`—then streams via `astream_doc_only` or `astream_hybrid` from `agent/app/rag/chains.py`. NDJSON: `{\"t\":\"chunk\",\"c\":\"...\"}` then `{\"t\":\"done\",\"answer\":\"...\",\"session_summary\":{...}}`. Backend forwards each line. Frontend appends chunks; human-speed reveal ~35 chars/sec—`frontend/src/pages/Dashboard.jsx:147-184`."*

### H. Failure Modes + Deterministic Guards

*"Invalid JSON: frontend validates before save; backend returns 422 with field details and example payload—`backend/app/main.py:validation_exception_handler`. Payload > 512 KB: 413 from RequestSizeLimitMiddleware. Max 1000 objects—`backend/app/models.py:MAX_OBJECTS_COUNT`."*

*"Missing geometry: `agent/app/graph_lc/nodes.py:geometry_guard_node`. When the question is about this drawing and spatial, and required layers (Highway, Plot Boundary) have objects but all lack geometry, we return a deterministic message—'Cannot determine because the current drawing does not provide geometric information for: Highway, Plot Boundary.' No LLM call."*

*"Empty session: backend sends empty list; Agent answers definition-only or states no drawing data. `backend/app/main.py:510`."*

*"Smalltalk: `agent/app/smalltalk.py:is_smalltalk()`. Short greetings (hi, thanks) with no domain keywords return a fixed friendly reply. No retrieval, no LLM. `agent/app/graph_lc/nodes.py:smalltalk_node`."*

*"Doc-only absence: when retrieved chunks don't contain the asked term, we return DOC_ONLY_EMPTY_MESSAGE. `agent/app/graph_lc/nodes.py:llm_node` lines 130-132."*

### I. Tradeoffs and Why They're Acceptable for MVP

*"Stateless Agent: simplifies scaling and security; session always supplied by backend. Acceptable: slight overhead per request."*

*"Keyword routing: fast, deterministic, no extra LLM. Acceptable: edge cases may misroute; we can refine keywords."*

*"Single-step retrieval + LLM: one retrieval, one call. Acceptable: latency and cost bounded; sufficient for hybrid RAG."*

*"No evidence in Agent response: designed but not implemented. WebSocket path works; REST path would fail. Acceptable for MVP if WS is primary."*

*"SQLite for users: fine for single-instance. Acceptable: swap to Postgres for scale."*

*"CORS allow_origins=[\"*\"]: acceptable for dev; narrow for production."*

### J. What I'd Improve Next (Practical, Prioritized)

1. **Evidence pipeline:** Add evidence construction in Agent finalize_node; return document_chunks and session_objects. Or make backend QAResponse.evidence optional and document current behavior.  
2. **REST /qa robustness:** Either build evidence from agent state or make evidence optional so REST path works.  
3. **Evidence UI:** Implement collapse-by-default Evidence section in Dashboard when evidence is returned.  
4. **Refresh token:** Add refresh token for long-lived sessions.  
5. **Rate limiting:** Add rate limits on auth and QA endpoints.  
6. **E2E tests:** Test full flow frontend → backend → agent.  
7. **Embedding config:** Make Chroma embedding model explicit in config.

---

## 4. "Defend This Design" — 12 Bullets

| Decision | Why | Alternative Considered | Tradeoff |
|----------|-----|------------------------|----------|
| **Stateless Agent** | Scaling, security, no user data in Agent | Stateful Agent with session storage | Extra bytes per request; backend must always supply session |
| **Redis for session** | TTL, fast, key-value fit | DB table, in-memory | Redis dependency; TTL means sessions expire |
| **TTL refresh on update** | Keeps active sessions alive | Fixed TTL only | Slightly more Redis writes |
| **Retrieval top-k 5** | Balance relevance vs noise | Higher k, lower k | Configurable in `agent/app/config.py:retrieval_top_k`; 5 is default |
| **Max 2 chunks per (source, page)** | Avoid same-page dominance | No limit | May drop marginally relevant chunks; `agent/app/rag/retrieval_postprocess.py:MAX_CHUNKS_PER_PAGE` |
| **Keyword routing** | No LLM, fast, deterministic | LLM-based routing | Edge cases; keywords need tuning |
| **Doc-only guard** | Prevents invented definitions | Always call LLM | May block when term paraphrased; `agent/app/guards/doc_only_guard.py:should_use_retrieved_for_doc_only` |
| **Payload limit 512 KB** | Protect backend | No limit | Large drawings rejected; `backend/app/models.py:MAX_PAYLOAD_SIZE_KB` |
| **Argon2 password hashing** | SOTA, no 72-byte limit | bcrypt, scrypt | Slightly slower; `backend/app/auth.py:17` |
| **Single LangGraph workflow** | One source of truth | Separate pipelines | All paths go through same nodes; guards short-circuit |
| **WebSocket primary for QA** | Streaming UX | REST only | REST path has evidence mismatch; WS works |
| **Session summary in prompt** | Reduce tokens, preserve context | Full JSON only | Summary may omit details; `agent/app/reasoning.py:compute_session_summary` |

---

## 5. Most Likely Interview Questions (15+) + Crisp Answers

### Security / Auth

**Q: How is authentication implemented?**  
A: JWT (HS256) with claims `sub` (username) and `user_id`. Created in `backend/app/auth.py:create_access_token()`. Passwords hashed with Argon2 via passlib—`backend/app/auth.py:17`. Login accepts username or email; `backend/app/user_service.py:authenticate()`.

**Q: Where is the JWT secret stored?**  
A: `JWT_SECRET_KEY` from env; default `change-this-secret-key-in-production`. `backend/app/config.py`. Not in repo; set in `.env`.

**Q: Is there a refresh token?**  
A: No. JWT expiry controlled by `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 60). User must re-login on expiry.

**Q: How does the WebSocket authenticate?**  
A: Token in query string: `/ws/qa?token=<jwt>`. Backend decodes with `decode_token()` before accepting—`backend/app/main.py:434-441`. No Bearer header for WS.

### Session Consistency & Concurrency

**Q: What happens if two tabs update session simultaneously?**  
A: Last write wins. Redis `SET` overwrites. No optimistic locking. Keys: `session:{user_id}:objects`, `session:{user_id}:meta`—`backend/app/session.py:28-33`.

**Q: How is session expiry handled?**  
A: TTL 3600s on both keys. Refreshed on every PUT. If expired, `get_objects` returns `[]`—`backend/app/session.py:64-78`.

### RAG Quality

**Q: How are PDFs chunked?**  
A: RecursiveCharacterTextSplitter, chunk_size 1000, overlap 200. `agent/app/ingest/ingestion.py`. Separators: `["\n\n", "\n", ". ", " ", ""]`.

**Q: What embedding model does Chroma use?**  
A: Chroma default; not explicitly set in code. `agent/app/chroma_client.py` and `config.py` do not specify embedding model. Unverified: Chroma default is typically all-MiniLM-L6-v2.

**Q: How do you prevent citation hallucination?**  
A: Doc-only guard: only call LLM if asked term appears in chunks—`agent/app/guards/doc_only_guard.py:should_use_retrieved_for_doc_only`. Otherwise return DOC_ONLY_EMPTY_MESSAGE. System prompt forbids inventing—`agent/app/rag/prompts.py:SYSTEM_PROMPT`.

**Q: What is retrieval_top_k and max_distance?**  
A: top_k=5, max_distance=None (no filter) by default. `agent/app/config.py`. Postprocess keeps max 2 chunks per (source, page)—`agent/app/rag/retrieval_postprocess.py`.

### Debuggability / Observability

**Q: What logging exists?**  
A: Python `logging` at INFO. Backend: main, session, auth, user_service. Agent: nodes, sync, ingestion. No structured logging or traces in code.

**Q: How do you test the agent?**  
A: `cd agent && pytest -q`. Tests: evidence_acceptance, followups, geometry_guard, graph, prompts, reasoning, retrieval, routing, smalltalk. Mock retrieval and chains for unit tests.

### Scale

**Q: How does this scale to multi-user?**  
A: Stateless Agent scales horizontally. Redis and SQLite shared. Session keys are per-user. SQLite write contention may limit backend; migrate to Postgres for high concurrency.

**Q: Is there caching?**  
A: No response caching. Chroma caches vectors. Document registry avoids re-ingesting unchanged PDFs.

**Q: What is the latency profile?**  
A: Single retrieval + single LLM call. Streaming reduces perceived latency. 60s timeout for Agent calls—`backend/app/main.py:515`.

### Failure Modes & Testing

**Q: How do you test invalid JSON?**  
A: `backend/tests/test_session_objects.py`—invalid object in list, missing type/layer. Backend returns 422 with field details.

**Q: How do you test the geometry guard?**  
A: `agent/tests/test_geometry_guard.py`, `test_evidence_acceptance.py`. Mock session objects with `geometry: null`; assert "Cannot determine" or "geometric information" in answer.

**Q: How do you test smalltalk?**  
A: `agent/tests/test_smalltalk.py`. POST `/answer` with "hi", assert no retrieval call, assert smalltalk response.

---

## 6. Demo Script (5–7 Minutes)

### Setup
- **What I say:** "I'll walk through the main flows: doc-only, json-only, hybrid, session update, and a guard case."
- **What I do:** Ensure logged in; Dashboard loaded; JSON editor has sample objects (or load from session).

### Doc-Only Example
- **What I say:** "First, a definition-style question. No session data needed."
- **What I click/type:** Type: *"What is the definition of a highway?"* Click **Ask**.
- **What I say:** "Routing sends this to DOC_ONLY. Retrieval runs; LLM gets question and chunks only. Answer comes from the PDF. If the term isn't in the chunks, we return a deterministic 'no definition found' message."

### JSON-Only Example
- **What I say:** "Now a count question. No retrieval."
- **What I click/type:** Type: *"How many Highway objects are in the current drawing?"* Click **Ask**.
- **What I say:** "Routing sends this to JSON_ONLY. Retrieval is skipped. Answer comes from session JSON and the session summary layer counts."

### Hybrid Example
- **What I say:** "Hybrid combines documents and drawing."
- **What I click/type:** Type: *"Does this property front a highway?"* Click **Ask**.
- **What I say:** "Routing sends this to HYBRID. Retrieval runs for the definition of 'highway' and 'fronting'; session JSON provides Highway and Plot Boundary layers. LLM combines both."

### Session Update Changes Answer
- **What I say:** "Session is ephemeral. I'll remove Highway and ask again."
- **What I click/type:** Edit JSON—remove Highway layer or set geometry to null. Click **Update Session**. Ask: *"Does this property front a highway?"*
- **What I say:** "Answer changes. Either 'cannot determine' if geometry is missing, or 'no' if Highway layer is gone. Session is always fresh from Redis."

### Evidence Behavior
- **What I say:** "Evidence is designed but not fully implemented. The Agent returns answer, query_mode, session_summary. The UI strips evidence markers from the answer text but doesn't render a dedicated Evidence section. If asked, I'd say we're iterating on the evidence pipeline."

### Guard Case: Missing Geometry
- **What I say:** "Guard: spatial question but no geometry."
- **What I click/type:** Ensure JSON has Highway and Plot Boundary but `geometry: null` on all objects. Ask: *"Does this property front a highway?"*
- **What I say:** "Geometry guard triggers. No LLM call. Deterministic message: 'Cannot determine because the current drawing does not provide geometric information for: Highway, Plot Boundary.' Implemented in `agent/app/graph_lc/nodes.py:geometry_guard_node`."

### Guard Case: Invalid JSON
- **What I say:** "Invalid JSON is caught before save."
- **What I click/type:** Break JSON (e.g. remove closing brace). Click **Update Session**.
- **What I say:** "Frontend validation blocks; or if it gets through, backend returns 422 with field details and an example payload."

---

## 7. Red Flags / Weak Spots

| Issue | What Code Does | If Asked, Say This |
|-------|----------------|--------------------|
| **Evidence mismatch** | Agent `AnswerResponse` has no `evidence`. Backend `QAResponse` requires it. REST `/qa` would fail Pydantic validation. | "Evidence pipeline is designed but not fully wired. WebSocket path works because it forwards raw NDJSON. We'd add evidence construction in the Agent or make it optional in the backend." |
| **Evidence UI missing** | Dashboard does not render Evidence section. `.qa-evidence` CSS exists but no JSX. | "Evidence display is on the roadmap. The answer text is cleaned of evidence markers; we'd add a collapsible Evidence block when the API returns it." |
| **REST /qa may fail** | `QAResponse(**agent_response)` with agent_response lacking `evidence` → ValidationError. | "In practice we use WebSocket for QA. The REST path needs a fix: either build evidence from agent state or make it optional." |
| **CORS allow_origins=["*"]** | `backend/app/main.py:162`, `agent/app/main.py:111`. | "Fine for dev. For production we'd narrow to specific origins." |
| **No rate limiting** | No rate limit middleware. | "We'd add rate limiting on auth and QA before production." |
| **SQLite for users** | `backend/app/database.py`. | "Adequate for MVP. We'd migrate to Postgres for horizontal scaling." |
| **No refresh token** | JWT only; expiry forces re-login. | "Simpler for MVP. We'd add refresh tokens for better UX." |
| **Chroma embedding not explicit** | `chroma_client.py` does not set embedding model. | "Uses Chroma default. We'd make it configurable for different models." |
| **No E2E tests** | Backend and Agent tests run separately; no cross-service E2E. | "Unit and integration tests per service. E2E would be the next step." |

---

*All claims verified against code. No speculation.*
