# AICI Hybrid RAG - Architecture Documentation

## System Overview

This document describes the architecture of the AICI Hybrid RAG system, which combines persistent knowledge from regulatory documents with ephemeral session-based drawing state.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Browser                                    │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ HTTP/HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Frontend (React + Vite)                             │
│                              Port: 3000                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │   Login     │  │ JSON Editor │  │  Q&A Panel  │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ /api/* (nginx proxy)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                                     │
│                           Port: 8000                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │  JWT Auth   │  │  Session    │  │  QA Route   │                         │
│  │  /auth/*    │  │  /session/* │  │  /qa        │                         │
│  └─────────────┘  └──────┬──────┘  └──────┬──────┘                         │
└──────────────────────────┼────────────────┼─────────────────────────────────┘
                           │                │
              ┌────────────┘                └────────────┐
              ▼                                          ▼
┌─────────────────────────┐              ┌─────────────────────────────────────┐
│       Redis             │              │          Agent (FastAPI)            │
│    Port: 6379           │              │            Port: 8001               │
│  ┌─────────────────┐    │              │  ┌─────────────┐  ┌─────────────┐  │
│  │ session:{uid}:  │    │              │  │  Retrieval  │  │  LLM Call   │  │
│  │   objects       │    │              │  │  (ChromaDB) │  │  (OpenAI)   │  │
│  └─────────────────┘    │              │  └──────┬──────┘  └─────────────┘  │
└─────────────────────────┘              └─────────┼───────────────────────────┘
                                                   │
                                                   ▼
                                         ┌─────────────────────┐
                                         │     ChromaDB        │
                                         │  (Persistent Vol)   │
                                         │  ┌───────────────┐  │
                                         │  │ PDF Embeddings│  │
                                         │  │ + Metadata    │  │
                                         │  └───────────────┘  │
                                         └─────────────────────┘
```

## Data Flow

### 1. Authentication Flow
```
User → Frontend → POST /auth/login → Backend → JWT Token → Frontend (localStorage)
```

### 2. Session Update Flow
```
User edits JSON → Frontend → PUT /session/objects → Backend → Redis (user-scoped key)
```

### 3. Question-Answer Flow
```
User asks question
    → Frontend: POST /qa
    → Backend: 
        1. Get session objects from Redis
        2. Forward {question, session_objects} to Agent
    → Agent:
        1. Retrieve relevant PDF chunks (ChromaDB)
        2. Build hybrid prompt (question + chunks + JSON)
        3. Call OpenAI LLM
        4. Return answer + evidence
    → Backend: Return response
    → Frontend: Display answer + evidence
```

## Key Design Decisions

### 1. Why JSON is NOT Embedded in Vector DB

**Decision:** Session JSON objects are stored in Redis, NOT in ChromaDB.

**Reasons:**
- JSON changes frequently (ephemeral state)
- Re-embedding on every change is expensive and slow
- JSON is small enough to include directly in prompts
- Each user has different JSON state (multi-user isolation)

**Alternative considered:** Embedding JSON with user-specific metadata
- Rejected due to: complexity, cost, latency, staleness issues

### 2. Why Retrieval is in the Agent Service

**Decision:** Vector search happens inside the Agent, not Backend.

**Reasons:**
- Agent owns the knowledge base (single responsibility)
- Reduces network calls (one call instead of two)
- Agent can optimize prompt construction with retrieval results
- Cleaner separation: Backend handles auth/sessions, Agent handles AI

### 3. Real-time Communication (WebSocket + Streaming)

**Decision:** Support real-time communication as specified: WebSocket for Q&A with streaming answers, plus REST fallback.

**Implementation:**
- **Frontend ↔ Backend:** WebSocket at `/ws/qa` (JWT in query). Client sends `{"question": "..."}`; backend proxies to the Agent’s streaming endpoint and forwards NDJSON chunks (`{"t":"chunk","c":"..."}` then `{"t":"done",...}`) so the user sees the answer as it is generated.
- **Backend ↔ Agent:** Backend calls Agent `POST /answer/stream`, which returns a streaming NDJSON response. Each request uses the current session state from Redis.
- **REST fallback:** `POST /qa` remains; the frontend uses it if the WebSocket is not connected. Each request still uses the latest session state.

### 4. Why Microservices (3 Services)

**Decision:** Frontend + Backend + Agent as separate containers.

**Reasons:**
- Natural separation of concerns
- Agent has heavy dependencies (ML libraries, ChromaDB)
- Backend is lightweight (auth, session, routing)
- Can scale services independently
- Follows challenge recommendation

**What we avoided:**
- Overkill microservices (separate retriever, embedder, chunker)
- Monolith (harder to maintain, test, scale)

## Service Responsibilities

| Service | Responsibilities |
|---------|-----------------|
| Frontend | UI, auth state, JSON editing, API calls |
| Backend | JWT auth, Redis sessions, QA orchestration |
| Agent | PDF ingestion, retrieval, prompt building, LLM calls |
| Redis | Ephemeral session storage (user-scoped) |
| ChromaDB | Persistent PDF embeddings + metadata |

## Security Considerations

1. **JWT tokens** expire after 60 minutes (configurable)
2. **User-scoped Redis keys** prevent cross-user data access
3. **CORS** configured for frontend origin
4. **Secrets** stored in `.env` (git-ignored)

## Scalability Notes

- **Redis:** Can be replaced with Redis Cluster for HA
- **ChromaDB:** Can be replaced with managed vector DB (Pinecone, Weaviate)
- **Agent:** Stateless, can run multiple instances behind load balancer
- **Backend:** Stateless (uses Redis), can scale horizontally
