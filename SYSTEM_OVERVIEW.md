# SYSTEM_OVERVIEW.md

**Repository:** `aici-conversational-rag`  
**Last Updated:** 2026-02-03  
**Author:** System Architecture Review

---

# 1. Purpose & Scope

## What Problem This System Solves

This system is a **Hybrid Retrieval-Augmented Generation (RAG)** application that answers user questions by combining two distinct knowledge sources:

1. **Persistent Knowledge** — Regulatory/planning documents (PDFs) pre-embedded in a vector database (ChromaDB). These embeddings remain fixed during a session.

2. **Ephemeral Session State** — User-provided JSON objects representing "drawing data" (e.g., walls, highways, plot boundaries). This data changes between queries and is stored per-user in Redis.

The system uses an LLM (OpenAI GPT-4o) to reason over both sources simultaneously, enabling questions like: *"Does this property front a highway?"* where the answer depends on both the regulatory definition of "highway" (from PDF) and the current drawing state (from JSON).

## Key User Flows

1. **Register/Login** → User creates account or logs in with JWT authentication
2. **Provide Drawing Objects** → User pastes/edits JSON in the frontend editor
3. **Save Session** → JSON is stored in Redis under the user's session
4. **Ask Question** → User submits natural-language query
5. **Hybrid RAG** → Agent retrieves relevant PDF chunks + uses session JSON to generate an answer with evidence citations

---

# 2. Repo Map (What Lives Where)

```
aici-conversational-rag/
├── agent/                    # AI Agent Service (Hybrid RAG)
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Settings (OpenAI key, ChromaDB path)
│   │   ├── llm_service.py    # OpenAI API integration
│   │   ├── prompts.py        # System/user prompt templates
│   │   ├── vector_store.py   # ChromaDB operations
│   │   ├── ingestion.py      # PDF text extraction + chunking
│   │   ├── document_registry.py  # Content hashing for idempotent sync
│   │   ├── sync_service.py   # Incremental document sync logic
│   │   ├── reasoning.py      # Session summary computation
│   │   └── models.py         # Pydantic request/response models
│   ├── tests/                # Agent unit tests
│   ├── Dockerfile
│   └── requirements.txt
│
├── backend/                  # Backend API Service (Auth + Session + Orchestration)
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Settings (JWT, Redis)
│   │   ├── auth.py           # JWT + Argon2 password hashing
│   │   ├── session.py        # Redis session storage + in-memory user store
│   │   └── models.py         # Pydantic models
│   ├── tests/                # Backend unit tests
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                 # React Web UI
│   ├── src/
│   │   ├── main.jsx          # React entry point
│   │   ├── App.jsx           # Root component (auth routing)
│   │   ├── context/AuthContext.jsx  # Auth state management
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx     # Login/Register UI
│   │   │   └── Dashboard.jsx     # JSON editor + Q&A panel
│   │   ├── services/api.js   # API client (fetch wrapper)
│   │   └── styles/           # CSS files
│   ├── index.html
│   ├── vite.config.js        # Vite config with proxy
│   ├── nginx.conf            # Production nginx config
│   ├── Dockerfile
│   └── package.json
│
├── data/                     # Data directory (mounted in Docker)
│   ├── pdfs/                 # PDF documents for ingestion
│   │   └── 240213 Permitted Development Rights.pdf
│   ├── chroma/               # ChromaDB persistence (auto-created)
│   └── sample_objects.json   # Sample drawing objects
│
├── docs/
│   └── ARCHITECTURE.md       # Architecture documentation
│
├── .github/
│   └── workflows/ci.yml      # GitHub Actions CI
│
├── docker-compose.yml        # Multi-service orchestration
├── env.example               # Environment variables template
└── README.md                 # Project documentation
```

---

# 3. Runtime Architecture (Boxes & Arrows)

## Services and Communication

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER (User)                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     React Frontend (Vite)                            │   │
│  │  • LoginPage.jsx (auth forms)                                        │   │
│  │  • Dashboard.jsx (JSON editor + Q&A chat)                            │   │
│  │  • AuthContext.jsx (JWT storage in localStorage)                     │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │ HTTP (port 3000)
                                    │ /api/* → proxied to backend
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NGINX (in frontend container)                       │
│  • Serves static React build                                                │
│  • Proxies /api/* to backend:8000                                           │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BACKEND SERVICE (FastAPI)                            │
│                            Port 8000                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Endpoints:                                                                 │
│    POST /auth/register    → Create user (in-memory store)                   │
│    POST /auth/login       → Return JWT token                                │
│    PUT  /session/objects  → Store JSON in Redis                             │
│    GET  /session/objects  → Retrieve JSON from Redis                        │
│    POST /qa               → Forward question to Agent                       │
│    GET  /health           → Check Redis + Agent connectivity                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Dependencies:                                                              │
│    • Redis (session storage)                                                │
│    • Agent Service (RAG pipeline)                                           │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
┌───────────────────────────────┐    ┌───────────────────────────────────────┐
│         REDIS (7-alpine)      │    │          AGENT SERVICE (FastAPI)      │
│           Port 6379           │    │              Port 8001                │
├───────────────────────────────┤    ├───────────────────────────────────────┤
│  Keys:                        │    │  Endpoints:                           │
│    session:{user_id}:objects  │    │    GET  /health         → Status      │
│    session:{user_id}:meta     │    │    GET  /sync/status    → Doc registry│
│                               │    │    POST /ingest         → Sync PDFs   │
│  TTL: 3600s (1 hour)          │    │    POST /answer         → Hybrid RAG  │
└───────────────────────────────┘    ├───────────────────────────────────────┤
                                     │  Internal Components:                 │
                                     │    • VectorStoreService (ChromaDB)    │
                                     │    • PDFIngestionService (pypdf)      │
                                     │    • DocumentRegistry (SHA256 hash)   │
                                     │    • LLMService (OpenAI API)          │
                                     │    • ReasoningService (JSON summary)  │
                                     └─────────────────┬─────────────────────┘
                                                       │
                                     ┌─────────────────┴─────────────────────┐
                                     │                                       │
                                     ▼                                       ▼
                          ┌───────────────────┐               ┌──────────────────┐
                          │     ChromaDB      │               │   OpenAI API     │
                          │  (Persistent)     │               │   (External)     │
                          ├───────────────────┤               ├──────────────────┤
                          │ Collection:       │               │ Model: gpt-4o    │
                          │  planning_documents│              │ Temp: 0.1        │
                          │                   │               │ Max tokens: 2000 │
                          │ Path: /data/chroma│               └──────────────────┘
                          └───────────────────┘
```

## Data Flow for Q&A Request

```
User Question + Session JSON
         │
         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│     Backend     │────▶│      Agent      │
│   Dashboard     │     │   POST /qa      │     │  POST /answer   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┴────────────────────────────────┐
                        │                                                                 │
                        ▼                                                                 ▼
              ┌─────────────────────┐                                    ┌─────────────────────┐
              │   VectorStore       │                                    │  ReasoningService   │
              │   .search(query)    │                                    │  .compute_summary() │
              │   → top-K chunks    │                                    │  → layer counts,    │
              └─────────────────────┘                                    │     flags, limits   │
                        │                                                └──────────┬──────────┘
                        │                                                           │
                        └──────────────────────┬────────────────────────────────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │     LLMService      │
                                    │  .generate_answer() │
                                    │                     │
                                    │  Prompt:            │
                                    │   • System prompt   │
                                    │   • Question        │
                                    │   • JSON objects    │
                                    │   • Session summary │
                                    │   • Retrieved chunks│
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │    OpenAI API       │
                                    │    gpt-4o           │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                        Answer + Evidence
```

---

# 4. Execution Paths (Step-by-Step)

## A) User Registers / Logs In

### Registration Flow

1. **Frontend** `LoginPage.jsx` → User fills form (username, email, password)
2. **API Call** → `authApi.register()` → `POST /api/auth/register`
3. **Backend** `main.py:register()` → Validates with Pydantic `UserRegister`
4. **Auth** `auth.py:get_password_hash()` → Argon2id hash
5. **UserStore** `session.py:UserStore.create_user()` → Stores in-memory dict
6. **Response** → `UserResponse(user_id, username, email)`

### Login Flow

1. **Frontend** → `authApi.login()` → `POST /api/auth/login` (form-urlencoded)
2. **Backend** → `main.py:login()` → OAuth2PasswordRequestForm
3. **UserStore** → `get_user(username)` → Retrieve user dict
4. **Auth** → `verify_password()` → Compare Argon2 hash
5. **JWT** → `create_access_token({sub: username, user_id})` → HS256 signed
6. **Response** → `Token(access_token="eyJ...")`
7. **Frontend** → `AuthContext.login()` → Stores token in `localStorage`

**State Storage:**
- Users: In-memory `UserStore._users` dict (NOT persisted)
- Token: `localStorage` in browser

---

## B) User Submits/Updates JSON Drawing Session

1. **Frontend** `Dashboard.jsx` → User edits JSON textarea
2. **JSON Validation** → `JSON.parse()` on every keystroke
3. **Save Button** → `handleSaveSession()` → `sessionApi.updateObjects()`
4. **API Call** → `PUT /api/session/objects` with `{ objects: [...] }`
5. **Backend** → `main.py:update_session_objects()` → Auth via `get_current_user()`
6. **Session Service** → `session.py:SessionService.set_objects(user_id, objects)`
7. **Redis** → `SET session:{user_id}:objects <JSON>` with TTL 3600s
8. **Response** → `SessionObjectsResponse(objects, object_count, updated_at)`

**State Storage:**
- Redis key: `session:{user_id}:objects` (JSON string)
- Redis key: `session:{user_id}:meta` (updated_at, object_count)
- TTL: 1 hour (configurable via `session_ttl_seconds`)

---

## C) User Asks a Q&A Question

### Step-by-Step

1. **Frontend** `Dashboard.jsx:handleAskQuestion()` → Auto-saves session first if needed
2. **API Call** → `qaApi.ask(question)` → `POST /api/qa`
3. **Backend** `main.py:ask_question()`:
   - Validates JWT token
   - Retrieves session objects from Redis: `session_service.get_objects(user_id)`
   - Calls agent: `httpx.post("http://agent:8001/answer", json={question, session_objects})`
4. **Agent** `main.py:answer_question()`:
   - **Validate JSON**: `reasoning_service.validate_json_schema(session_objects)`
   - **Compute Summary**: `reasoning_service.compute_session_summary()` → layer counts, flags
   - **Retrieve Chunks**: `vector_store.search(query, top_k=5)`
   - **Build Prompt**: `prompts.py:build_user_prompt()` → combines question + JSON + summary + chunks
   - **Call LLM**: `llm_service.generate_answer()` → OpenAI API
   - **Extract Evidence**: `reasoning_service.extract_layers_used()`
5. **Response Path** → `AnswerResponse` → Backend → Frontend
6. **Frontend** → Adds message to `messages` state array, displays in chat

### Request/Response Models

**Backend QARequest:**
```json
{ "question": "Does this property front a highway?" }
```

**Agent AnswerRequest:**
```json
{
  "question": "Does this property front a highway?",
  "session_objects": [{ "layer": "Highway", ... }, ...]
}
```

**Agent AnswerResponse:**
```json
{
  "answer": "Based on the drawing, yes, the property fronts a highway...",
  "evidence": {
    "document_chunks": [
      { "chunk_id": "...", "source": "...", "page": "6", "section": "General Issues", "text_snippet": "..." }
    ],
    "session_objects": { "layers_used": ["Highway", "Plot Boundary"], "object_indices": [0, 2] }
  },
  "session_summary": {
    "layer_counts": { "Highway": 2, "Plot Boundary": 1, ... },
    "plot_boundary_present": true,
    "highways_present": true,
    "total_objects": 7,
    "limitations": []
  }
}
```

---

## D) Permanent Knowledge Ingestion / Retrieval

### Ingestion Pipeline (On Agent Startup)

1. **Agent Startup** → `main.py:lifespan()` runs
2. **Initialize Registry** → `DocumentRegistry(registry_path)` loads `document_registry.json`
3. **Initialize Sync Service** → `DocumentSyncService(registry, ingestion, vector_store)`
4. **Run Sync** → `sync_service.sync(delete_missing=False)`

### Sync Algorithm (Idempotent)

```python
for pdf in data/pdfs/*.pdf:
    content_hash = SHA256(pdf_bytes)
    status = registry.get_status(pdf.name, content_hash)
    
    if status == NEW:
        chunks = ingest_and_chunk(pdf)
        vector_store.add_documents(chunks)
        registry.register(pdf.name, content_hash, chunk_ids)
    
    elif status == UNCHANGED:
        skip()  # No action needed
    
    elif status == UPDATED:
        old_chunk_ids = registry.get_chunk_ids(pdf.name)
        vector_store.delete_by_ids(old_chunk_ids)
        chunks = ingest_and_chunk(pdf)
        vector_store.add_documents(chunks)
        registry.register(pdf.name, content_hash, chunk_ids)
```

### PDF Processing Details

1. **Extract Text** → `ingestion.py:PDFIngestionService.extract_text_from_pdf()` using `pypdf`
2. **Chunk** → `RecursiveCharacterTextSplitter(chunk_size=1000, overlap=200)`
3. **Detect Section** → Heuristic pattern matching for "Class A", "Class B", etc.
4. **Metadata** → `{ source, page, section, chunk_index }`
5. **Chunk ID** → `{filename}_{page:03d}_{counter:04d}` (e.g., `240213 Permitted Development Rights_006_0042`)

### Retrieval Pipeline (During Q&A)

1. **Query** → `vector_store.search(query_text, top_k=5)`
2. **ChromaDB** → Semantic similarity search (default embedding model)
3. **Return** → List of `{ id, text, source, page, section, distance }`

---

# 5. Backend Deep Dive

## Framework

**FastAPI** 0.115+ with Python 3.11

## Entry Point

`backend/app/main.py` — Creates FastAPI app with lifespan handler

## API Endpoints

| Method | Path | Handler | Request Model | Response Model |
|--------|------|---------|---------------|----------------|
| POST | `/auth/register` | `register()` | `UserRegister` | `UserResponse` |
| POST | `/auth/login` | `login()` | `OAuth2PasswordRequestForm` | `Token` |
| PUT | `/session/objects` | `update_session_objects()` | `SessionObjects` | `SessionObjectsResponse` |
| GET | `/session/objects` | `get_session_objects()` | — | `SessionObjectsResponse` |
| POST | `/qa` | `ask_question()` | `QARequest` | `QAResponse` |
| GET | `/health` | `health_check()` | — | `HealthResponse` |
| GET | `/` | `root()` | — | JSON dict |

## Authentication

**Location:** `backend/app/auth.py`

- **Password Hashing:** Argon2id via `passlib.context.CryptContext`
- **JWT Creation:** `python-jose` with HS256 algorithm
- **Token Expiry:** 60 minutes (configurable)
- **Token Validation:** `get_current_user()` dependency extracts `TokenData` from Bearer token

**Secret Key Source:** Environment variable `JWT_SECRET_KEY` (default: `"change-this-secret-key-in-production"`)

## User Storage

**Location:** `backend/app/session.py:UserStore`

- **Storage:** In-memory Python dict (`_users`, `_email_index`)
- **NOT PERSISTENT** — Users reset on container restart
- **Schema:**
  ```python
  {
      "user_id": "uuid",
      "username": "string",
      "email": "string",
      "hashed_password": "argon2 hash"
  }
  ```

## Session Storage (Redis)

**Location:** `backend/app/session.py:SessionService`

- **Connection:** `redis.Redis(host, port, db)`
- **Keys:**
  - `session:{user_id}:objects` — JSON array of drawing objects
  - `session:{user_id}:meta` — Metadata (updated_at, object_count)
- **TTL:** 3600 seconds

## Error Handling

- Pydantic validation errors → 422 Unprocessable Entity
- Authentication errors → 401 Unauthorized with `WWW-Authenticate: Bearer`
- Agent service errors → 502 Bad Gateway or 503 Service Unavailable
- All errors logged via `logging.getLogger(__name__)`

---

# 6. Agent Deep Dive

## Entry Point

`agent/app/main.py` — FastAPI app with lifespan handler for startup sync

## API Endpoints

| Method | Path | Handler | Request Model | Response Model |
|--------|------|---------|---------------|----------------|
| GET | `/health` | `health_check()` | — | `HealthResponse` |
| GET | `/sync/status` | `get_sync_status()` | — | `SyncStatusResponse` |
| POST | `/ingest` | `ingest_documents()` | `IngestRequest` | `IngestResponse` |
| POST | `/answer` | `answer_question()` | `AnswerRequest` | `AnswerResponse` |
| GET | `/` | `root()` | — | JSON dict |

## Tools / Retrieval Logic

### Vector Store (ChromaDB)

**Location:** `agent/app/vector_store.py:VectorStoreService`

- **Client:** `chromadb.PersistentClient(path="/data/chroma")`
- **Collection:** `planning_documents`
- **Search:** `collection.query(query_texts=[query], n_results=top_k)`
- **Embedding:** ChromaDB's default embedding function (all-MiniLM-L6-v2)

### Prompt Building

**Location:** `agent/app/prompts.py`

**System Prompt:** Defines agent behavior rules (7 rules about treating documents as authoritative, JSON as ground truth, etc.)

**User Prompt Template:**
```
User question: {question}

Session drawing objects (current JSON):
{json_objects_pretty}

Derived session summary:
- Layer counts: {layer_counts}
- Plot boundary present: {plot_boundary_present}
- Highways present: {highways_present}
- Known limitations: {limitations}

Retrieved regulatory excerpts:
{retrieved_chunks_formatted}

Task: ...
```

### LLM Call

**Location:** `agent/app/llm_service.py:LLMService`

```python
response = self.client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ],
    temperature=0.1,
    max_tokens=2000
)
```

## Memory / History Handling

**Chat history is NOT stored.** Each question is independent. The frontend maintains a local `messages` array for display only — it is not sent to the backend or used for context.

## Configuration

**Location:** `agent/app/config.py`

| Variable | Default | Source |
|----------|---------|--------|
| `openai_api_key` | `""` | `OPENAI_API_KEY` |
| `openai_model` | `"gpt-4o"` | — |
| `chroma_persist_directory` | `"/data/chroma"` | `CHROMA_PERSIST_DIRECTORY` |
| `chroma_collection_name` | `"planning_documents"` | — |
| `pdf_data_directory` | `"/data/pdfs"` | `PDF_DATA_DIRECTORY` |
| `retrieval_top_k` | `5` | — |
| `chunk_size` | `1000` | — |
| `chunk_overlap` | `200` | — |

---

# 7. Frontend Deep Dive

## Framework

**React 19** with **Vite 6** (build tool)

## Entry Point

`frontend/src/main.jsx` → Wraps App in `AuthProvider`

## Routes / Pages

| Path | Component | Description |
|------|-----------|-------------|
| `/` | `App.jsx` | Conditional render based on auth state |
| — | `LoginPage.jsx` | Login/Register forms (shown when not authenticated) |
| — | `Dashboard.jsx` | JSON editor + Q&A panel (shown when authenticated) |

## Components

### LoginPage (`frontend/src/pages/LoginPage.jsx`)
- Two tabs: Sign In / Register
- Form validation
- Calls `authApi.register()` or `authApi.login()`
- On success: calls `login(token, user)` from AuthContext

### Dashboard (`frontend/src/pages/Dashboard.jsx`)
- **Left Panel:** JSON textarea with validation indicator
- **Right Panel:** Q&A chat messages
- Sample objects pre-loaded
- Auto-saves session before asking questions

### AuthContext (`frontend/src/context/AuthContext.jsx`)
- Stores `user`, `token`, `loading` state
- `login()` → saves to localStorage
- `logout()` → clears localStorage
- `isAuthenticated` computed from `!!token`

## API Client

**Location:** `frontend/src/services/api.js`

- **Base URL:** `/api` (proxied by Vite in dev, nginx in prod)
- **Token Storage:** `localStorage.getItem('token')`
- **Auth Header:** `Authorization: Bearer ${token}`

### Endpoints Called

| Function | Method | Path |
|----------|--------|------|
| `authApi.register()` | POST | `/api/auth/register` |
| `authApi.login()` | POST | `/api/auth/login` |
| `sessionApi.getObjects()` | GET | `/api/session/objects` |
| `sessionApi.updateObjects()` | PUT | `/api/session/objects` |
| `qaApi.ask()` | POST | `/api/qa` |
| `healthApi.check()` | GET | `/api/health` |

## State Management

- **Auth State:** React Context (`AuthContext`)
- **Local Component State:** `useState` hooks
- **No Redux/Zustand** — simple enough for local state

---

# 8. Data & Knowledge Base

## What is "Permanent Knowledge"

PDF regulatory documents pre-embedded in ChromaDB. Currently:
- `data/pdfs/240213 Permitted Development Rights.pdf` (UK planning regulations)

These embeddings are:
- Created once during agent startup (or on `/ingest`)
- Shared across all users
- Read-only during Q&A (no user modifications)

## Document Source

**Location:** `data/pdfs/` directory (mounted as Docker volume)

**How to add documents:**
1. Copy PDF file to `data/pdfs/`
2. Restart agent container (auto-syncs on startup)
3. Or call `POST /ingest` endpoint

**No admin UI exists** — document management is file-based.

## Ingestion Pipeline

1. **PDF Reading:** `pypdf.PdfReader` extracts text page-by-page
2. **Chunking:** `langchain_text_splitters.RecursiveCharacterTextSplitter`
   - `chunk_size=1000`, `chunk_overlap=200`
   - Separators: `["\n\n", "\n", ". ", " ", ""]`
3. **Section Detection:** Heuristic pattern matching for "Class A/B/C...", "General Issues", etc.
4. **Metadata:** `{ source: filename, page: "1", section: "Class A", chunk_index: 42 }`
5. **ID Generation:** `{filename}_{page:03d}_{counter:04d}`

## Content Hash Registry

**Location:** `agent/app/document_registry.py`

- **Hash Algorithm:** SHA256 of entire PDF file bytes
- **Storage:** `data/chroma/document_registry.json`
- **Record Fields:**
  ```json
  {
    "source_id": "240213 Permitted Development Rights.pdf",
    "content_hash": "a3f2b8c9...",
    "chunk_ids": ["..._001_0001", "..._001_0002", ...],
    "version": 1,
    "last_ingested_at": "2026-02-03T18:30:00Z",
    "page_count": 50,
    "chunk_count": 156
  }
  ```

## Retrieval Pipeline

1. **Query:** Natural language question
2. **Semantic Search:** ChromaDB `collection.query(query_texts=[query], n_results=5)`
3. **Results:** Top-K chunks with metadata
4. **No Reranking** — uses raw similarity scores
5. **Prompt Injection Protection:** None explicitly implemented (relies on system prompt rules)

---

# 9. Database & Storage

## Databases

| Database | Purpose | Persistence |
|----------|---------|-------------|
| **Redis 7** | Session objects, metadata | Docker volume `redis_data` |
| **ChromaDB** | Document embeddings | Docker volume `chroma_data` + `/data/chroma` |
| **In-memory dict** | User credentials | NOT persisted (container restart = data loss) |

## Redis Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `session:{user_id}:objects` | String (JSON) | 3600s | Drawing objects array |
| `session:{user_id}:meta` | String (JSON) | 3600s | `{ updated_at, object_count }` |

## ChromaDB Collection

| Collection | Metadata |
|------------|----------|
| `planning_documents` | `{ description: "Planning/regulatory documents for RAG" }` |

**Document Schema:**
- `id`: Unique chunk ID
- `document`: Chunk text
- `metadata`: `{ source, page, section, chunk_index }`

## File Storage

| Path | Contents |
|------|----------|
| `/data/pdfs/` | Source PDF documents |
| `/data/chroma/` | ChromaDB persistence files |
| `/data/chroma/document_registry.json` | Document hash registry |
| `/data/sample_objects.json` | Sample drawing objects (reference only) |

## Migrations

**None** — No traditional SQL database, no migrations.

---

# 10. Docker & Local Dev

## Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `redis` | `redis:7-alpine` | 6379 | Session storage |
| `agent` | `./agent` | 8001 | RAG pipeline |
| `backend` | `./backend` | 8000 | Auth + API |
| `frontend` | `./frontend` | 3000→80 | React UI |

## Running with Docker

```bash
# Clone and setup
git clone https://github.com/NurbukeTeker/aici-conversational-rag.git
cd aici-conversational-rag
cp env.example .env
# Edit .env to add OPENAI_API_KEY

# Build and run
docker compose up --build

# Access
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
# Agent API: http://localhost:8001/docs
```

## Running Locally (Without Docker)

```bash
# Terminal 1: Redis
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 2: Agent
cd agent
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export CHROMA_PERSIST_DIRECTORY=./data/chroma
export PDF_DATA_DIRECTORY=./data/pdfs
uvicorn app.main:app --host 0.0.0.0 --port 8001

# Terminal 3: Backend
cd backend
pip install -r requirements.txt
export REDIS_HOST=localhost
export AGENT_SERVICE_URL=http://localhost:8001
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 4: Frontend
cd frontend
npm install
npm run dev
# Access: http://localhost:3000
```

## Environment Variables

**From `env.example`:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key for LLM |
| `JWT_SECRET_KEY` | No | `"change-this..."` | JWT signing key |
| `JWT_ALGORITHM` | No | `"HS256"` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Token expiry |
| `REDIS_HOST` | No | `"redis"` | Redis hostname |
| `REDIS_PORT` | No | `6379` | Redis port |
| `REDIS_DB` | No | `0` | Redis database |
| `AGENT_SERVICE_URL` | No | `"http://agent:8001"` | Agent URL |
| `CHROMA_PERSIST_DIRECTORY` | No | `"/data/chroma"` | ChromaDB path |
| `PDF_DATA_DIRECTORY` | No | `"/data/pdfs"` | PDF source path |

---

# 11. Tests & CI

## Test Coverage

### Backend Tests (`backend/tests/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_auth.py` | Password hashing, JWT creation/decoding | Auth module |
| `test_models.py` | Pydantic model validation | Models |

### Agent Tests (`agent/tests/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_reasoning.py` | Session summary, JSON validation, layer extraction | ReasoningService |
| `test_prompts.py` | Prompt formatting | Prompt templates |

## Running Tests Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
pytest -v

# Agent
cd agent
pip install -r requirements.txt
export CHROMA_PERSIST_DIRECTORY=./test_chroma
export PDF_DATA_DIRECTORY=./test_data
pytest -v
```

## GitHub Actions CI

**Location:** `.github/workflows/ci.yml`

**Triggers:** Push to `main`, PR to `main`, manual dispatch

**Jobs:**

| Job | Runs | Steps |
|-----|------|-------|
| `backend` | `ubuntu-latest` | Install deps → `pytest -q` |
| `agent` | `ubuntu-latest` | Install deps → `pytest -q` (with empty API key) |
| `frontend` | `ubuntu-latest` | `npm install` → `npm run build` |
| `docker-build` | `ubuntu-latest` | `docker compose build` |

---

# 12. Gaps / Risks / TODOs

## Missing Features vs Intended Scope

| Feature | Status | Notes |
|---------|--------|-------|
| **Chat History Persistence** | ❌ Not implemented | Each question is independent; frontend only stores local array |
| **Document Ingestion UI/Admin** | ❌ Not implemented | File-based only; no upload endpoint |
| **User Persistence** | ❌ Not implemented | In-memory dict; users lost on restart |
| **Refresh Tokens** | ❌ Not implemented | Only access tokens; re-login required after expiry |
| **Rate Limiting** | ❌ Not implemented | OpenAI calls unprotected |
| **Streaming Responses** | ❌ Not implemented | Full response only |

## Security Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **JWT secret in env** | Medium | Use proper secrets management in production |
| **CORS allow all origins** | Medium | Restrict to specific domains in production |
| **No input sanitization for prompts** | Low | System prompt rules mitigate; add explicit validation |
| **No HTTPS** | High | Add TLS termination (nginx or load balancer) |
| **Users in memory** | High | Replace with PostgreSQL/MongoDB |

## Reliability Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Agent OOM on large PDFs** | Service crash | Add memory limits; paginate ingestion |
| **ChromaDB single instance** | No HA | Use managed vector DB for production |
| **Redis no persistence config** | Data loss | Enable AOF/RDB in production |

## Recommended TODOs

1. **Persist users** — Replace `UserStore` with proper database
2. **Add rate limiting** — Protect `/qa` endpoint (OpenAI costs)
3. **Implement refresh tokens** — Better UX for token expiry
4. **Add streaming** — Stream LLM responses for better UX
5. **Add document upload** — Admin endpoint to upload PDFs
6. **Add integration tests** — Test full flows with pytest + docker

---

# 13. "Is This Correct?" Checklist

Use this checklist to verify system correctness:

## Infrastructure ✓

- [ ] `docker compose up --build` completes without errors
- [ ] All 4 containers are running: `docker ps` shows redis, agent, backend, frontend
- [ ] Health checks pass: `curl http://localhost:8000/health` returns `{"status":"healthy"}`
- [ ] Agent health: `curl http://localhost:8001/health` returns `{"status":"healthy"}`

## Authentication ✓

- [ ] Can register new user: `POST /auth/register` returns 201
- [ ] Can login: `POST /auth/login` returns JWT token
- [ ] Protected endpoints reject without token: `GET /session/objects` returns 401
- [ ] Protected endpoints accept with token: `Authorization: Bearer <token>` returns 200

## Session Management ✓

- [ ] Can save JSON objects: `PUT /session/objects` returns 200
- [ ] Can retrieve saved objects: `GET /session/objects` returns same objects
- [ ] Different users have isolated sessions

## Document Ingestion ✓

- [ ] PDF exists: `ls data/pdfs/` shows PDF file
- [ ] Sync ran: Agent logs show "Sync result: X new, Y updated"
- [ ] Vector store has documents: `GET /sync/status` shows `documents_count > 0`
- [ ] Registry exists: `cat data/chroma/document_registry.json` shows records

## RAG Retrieval ✓

- [ ] Q&A returns answer: `POST /qa` with `{"question":"What is a highway?"}` returns non-empty answer
- [ ] Evidence included: Response contains `document_chunks` with sources
- [ ] Session objects used: Response contains `session_objects` evidence (if relevant)

## Frontend ✓

- [ ] Login page loads: `http://localhost:3000` shows login form
- [ ] Can register and login
- [ ] Dashboard shows JSON editor and Q&A panel
- [ ] JSON validation works (invalid JSON shows error)
- [ ] Can ask question and see answer

## CI/CD ✓

- [ ] GitHub Actions pass on push to main
- [ ] All jobs green: backend, agent, frontend, docker-build

---

# How to Verify in 15 Minutes

```bash
# 1. Start system (5 min)
cd aici-conversational-rag
cp env.example .env
# Add your OPENAI_API_KEY to .env
docker compose up --build -d

# 2. Wait for health (1 min)
sleep 60
curl http://localhost:8000/health
# Expected: {"status":"healthy","redis_connected":true,"agent_available":true}

# 3. Check document ingestion (1 min)
curl http://localhost:8001/sync/status
# Expected: registered_documents > 0, total_chunks > 0

# 4. Register user (1 min)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@test.com","password":"password123"}'

# 5. Login (1 min)
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test&password=password123" | jq -r .access_token)

# 6. Save session (1 min)
curl -X PUT http://localhost:8000/session/objects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"objects":[{"layer":"Highway","type":"line"}]}'

# 7. Ask question (3 min)
curl -X POST http://localhost:8000/qa \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is a highway in planning terms?"}'
# Expected: JSON with answer + evidence

# 8. Open frontend (2 min)
# Browser: http://localhost:3000
# Login with test/password123
# Edit JSON, ask a question, verify answer appears

echo "✅ System verified!"
```

---

**End of SYSTEM_OVERVIEW.md**
