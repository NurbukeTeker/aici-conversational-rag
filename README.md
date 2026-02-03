# AICI Conversational RAG

A hybrid Retrieval-Augmented Generation system combining persistent knowledge from regulatory documents with ephemeral session-based JSON object state.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│    Backend      │────▶│     Agent       │
│   (React App)   │     │   (FastAPI)     │     │   (FastAPI)     │
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
| Backend | 8000 | JWT auth, Redis session management, query orchestration |
| Agent | 8001 | PDF ingestion, vector store, hybrid RAG pipeline |
| Redis | 6379 | Ephemeral session storage (JSON objects, chat history) |

## Key Features

- **Persistent Knowledge**: PDF documents embedded in ChromaDB vector store
- **Ephemeral State**: Session JSON objects stored in Redis (not vectorized)
- **Hybrid RAG**: Combines retrieved document chunks with current session state
- **JWT Authentication**: Secure user sessions
- **Citation Support**: Responses include document chunk references

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API Key

### Setup

1. Clone the repository:
```bash
git clone <repo-url>
cd aici-conversational-rag
```

2. Create environment file:
```bash
cp env.example .env
# Edit .env and add your OPENAI_API_KEY
```

3. Place PDF documents in `data/pdfs/` directory

4. Start all services:
```bash
docker-compose up --build
```

5. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000/docs
   - Agent API: http://localhost:8001/docs

## API Endpoints

### Backend (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login and get JWT token |
| PUT | `/session/objects` | Update session JSON objects |
| GET | `/session/objects` | Get current session objects |
| POST | `/qa` | Ask a question (hybrid RAG) |

### Agent (Port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/answer` | Process question with RAG |
| POST | `/ingest` | Ingest PDF documents |
| GET | `/health` | Health check |

## Development

### Branch Strategy

- `main` - Stable, production-ready
- `feat/agent-hybrid-rag` - Agent service development
- `feat/backend-auth-session` - Backend service development
- `feat/frontend-ui` - Frontend development

### Commit Convention

```
feat(scope): description
fix(scope): description
chore(scope): description
docs: description
```

## License

MIT
