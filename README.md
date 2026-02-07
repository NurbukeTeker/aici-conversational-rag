# AICI Hybrid RAG Challenge

A hybrid Retrieval-Augmented Generation system that combines **persistent knowledge** from planning/regulatory PDF documents with **ephemeral session state** (drawing objects in JSON) to answer user questions with grounded, auditable responses.

## 🎯 What This System Does

1. **Persistent Knowledge**: PDF documents (e.g., UK Permitted Development Rights) are embedded into a ChromaDB vector database once
2. **Ephemeral State**: Each user's drawing objects (JSON) are stored in Redis per session — NOT embedded
3. **Hybrid Answers**: Questions are answered by retrieving relevant PDF rules AND reasoning over the current JSON state
4. **Multi-User Isolation**: Each user has their own session; same question + different JSON = different answer

## Mapping to Challenge Requirements

| Challenge Requirement | Implementation |
|----------------------|----------------|
| Persistent knowledge | PDF embeddings stored in ChromaDB (fixed, global) |
| Ephemeral state | User-scoped JSON in Redis (per session, not embedded) |
| Hybrid reasoning | Agent prompt combines retrieved chunks + current JSON |
| Multi-user sessions | JWT authentication + Redis keys scoped by user_id |
| Modular system | Frontend + Backend + Agent as separate services |
| Real-time communication | WebSocket for streaming Q&A; each request uses latest session state |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│    Backend      │────▶│     Agent       │
│   (React/Vite)  │     │   (FastAPI)     │     │   (FastAPI)     │
│   Port: 3000    │     │   Port: 8000    │     │   Port: 8001    │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                                 ▼                       ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │     Redis       │     │   ChromaDB      │
                        │ (Session Store) │     │ (Vector Store)  │
                        └─────────────────┘     └─────────────────┘
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | React app with login, JSON editor, Q&A interface |
| Backend | 8000 | JWT auth, Redis session management, QA orchestration |
| Agent | 8001 | PDF ingestion, vector store, hybrid RAG pipeline |
| Redis | 6379 | Ephemeral session storage (user-scoped JSON) |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API Key

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/NurbukeTeker/aici-conversational-rag.git
cd aici-conversational-rag
```

2. **Create environment file:**
```bash
cp env.example .env
# Edit .env and add your OPENAI_API_KEY
```

3. **Place PDF documents in `data/pdfs/` directory**
   - Example: UK Permitted Development Rights PDF

4. **Start all services:**
```bash
docker-compose up --build
```

5. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API Docs: http://localhost:8000/docs
   - Agent API Docs: http://localhost:8001/docs

> **Note on PDF Ingestion:** PDF ingestion runs automatically on agent startup if the vector store is empty. The `/ingest` endpoint is provided for manual re-indexing during development.

## Example Queries

Try these questions with the sample JSON (pre-filled in the frontend):

| Question | What It Tests |
|----------|---------------|
| "Does this property front a highway?" | Checks `Highway` layer in JSON + PDF definition of "highway" |
| "What are the rules for rear extensions?" | Retrieves Class A rules from PDF |
| "Can I build an extension beyond the rear wall?" | Combines PDF rules with `Walls` layer analysis |
| "What permitted development rights apply to this plot?" | Uses `Plot Boundary` + PDF Class rules |
| "Is a planning application required for a new door?" | Checks `Doors` layer + PDF conditions |

### Example: What the Agent Sees

When you ask "Does this property front a highway?", the agent receives:

```
Question: "Does this property front a highway?"

Session JSON layers: Highway (2), Plot Boundary (1), Walls (2), Doors (1), Windows (1)

Retrieved document excerpt:
[DOC: permitted_development.pdf | p6 | chunk: general_issues_highway]
"Highway" - is a public right of way such as a public road, public footpath 
and bridleway. For the purposes of the Order it also includes unadopted 
streets or private ways.

→ Agent reasons: JSON contains "Highway" layer → property fronts a highway
```

## API Endpoints

### Backend (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login and get JWT token |
| PUT | `/session/objects` | Update session JSON objects |
| GET | `/session/objects` | Get current session objects |
| POST | `/qa` | Ask a question (hybrid RAG, non-streaming) |
| WebSocket | `/ws/qa` | Real-time Q&A with streaming answers (token in query) |
| GET | `/health` | Health check |

### Agent (Port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/answer` | Process question with hybrid RAG (full response) |
| POST | `/answer/stream` | Same as `/answer` but streams response as NDJSON |
| POST | `/ingest` | Manually trigger PDF re-ingestion |
| GET | `/health` | Health check (includes vector store status) |

## Security Considerations

| Aspect | Implementation |
|--------|----------------|
| Authentication | JWT tokens with configurable expiry (default: 60 min) |
| Token refresh | Not implemented (out of scope for challenge) |
| User isolation | Redis keys scoped by `session:{user_id}:objects` |
| Secrets | Stored in `.env` file (git-ignored) |
| CORS | Configured for frontend origin |

## Design Decisions

### Why JSON is NOT Embedded in Vector DB

The drawing JSON is stored in Redis, **not** ChromaDB:
- JSON changes frequently during a session
- Re-embedding on every edit is expensive and slow
- JSON is small enough to include directly in LLM prompts
- Multi-user isolation requires user-scoped storage

### Why Retrieval is in the Agent Service

Vector search happens inside the Agent:
- Agent owns the knowledge base (single responsibility)
- Reduces network roundtrips
- Cleaner separation: Backend = auth/sessions, Agent = AI

### Real-time Communication

The backend supports **real-time communication** with the AI Agent as required by the challenge:
- **WebSocket** (`/ws/qa`): The frontend opens a WebSocket (with JWT in query). Questions are sent over the socket; the backend streams the Agent’s answer back token-by-token so the user sees the response as it is generated.
- **REST** (`POST /qa`): Still available; the frontend falls back to it if the WebSocket is unavailable. Each request uses the latest session state.
- Communication with the Agent uses the current session state on every request; streaming is implemented via the Agent’s `/answer/stream` endpoint, which the backend proxies to the client.

### Performance Optimization

To reduce token usage, a lightweight session summary (layer counts, presence flags) is computed on JSON update and included in prompts. This avoids sending the full JSON for simple presence checks.

## Project Structure

```
├── frontend/          # React + Vite app
│   ├── src/
│   │   ├── pages/     # LoginPage, Dashboard
│   │   ├── context/   # AuthContext
│   │   └── services/  # API client
│   └── Dockerfile
├── backend/           # FastAPI backend
│   ├── app/
│   │   ├── main.py    # Endpoints
│   │   ├── auth.py    # JWT auth
│   │   └── session.py # Redis session
│   └── Dockerfile
├── agent/             # FastAPI agent
│   ├── app/
│   │   ├── main.py    # /answer endpoint
│   │   ├── ingestion.py
│   │   ├── vector_store.py
│   │   ├── prompts.py
│   │   └── reasoning.py
│   └── Dockerfile
├── data/
│   ├── pdfs/          # Place PDF files here
│   └── sample_objects.json
├── docs/
│   └── ARCHITECTURE.md
├── docker-compose.yml
├── env.example
└── README.md
```

## Troubleshooting

### "Agent service unavailable"
- Check if agent container is running: `docker-compose ps`
- Check agent logs: `docker-compose logs agent`
- Ensure `OPENAI_API_KEY` is set in `.env`

### "No relevant excerpts found"
- Ensure PDF files are in `data/pdfs/`
- Trigger re-ingestion: `curl -X POST http://localhost:8001/ingest`
- Check agent logs for ingestion errors

### "Invalid JSON" error
- Ensure JSON textarea contains valid JSON array
- Check browser console for parse errors
- Use the sample JSON as a starting point

### "Incorrect username or password"
- User credentials are stored in-memory for simplicity (challenge scope). In production, this would be replaced by a persistent database.
- Register a new user after container restart

### CORS errors
- Backend has `allow_origins=["*"]` configured
- If issues persist, check browser network tab for actual error

## Development

### Branch Strategy

- `main` - Stable, production-ready
- `feat/agent-hybrid-rag` - Agent service
- `feat/backend-auth-session` - Backend service
- `feat/frontend-ui` - Frontend
- `chore/docker-compose` - Docker configuration

### Commit Convention

```
feat(scope): description
fix(scope): description
chore(scope): description
docs: description
```

### Running Locally (without Docker)

```bash
# Terminal 1: Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2: Agent
cd agent
pip install -r requirements.txt
uvicorn app.main:app --port 8001

# Terminal 3: Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# Terminal 4: Frontend
cd frontend
npm install
npm run dev
```

## Demo Script

### Multi-User Isolation Test

1. **User A**: Login → Update JSON (add Highway layer) → Ask "Does this front a highway?" → Answer: Yes
2. **User B**: Login → Update JSON (remove Highway layer) → Same question → Answer: No
3. **User A**: Update JSON (remove Highway) → Same question → Answer changes to No

This proves:
- ✅ Each user has isolated session state
- ✅ Answers depend on current JSON
- ✅ Same question + different JSON = different answer

## License

MIT
