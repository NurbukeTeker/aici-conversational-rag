"""Agent service - FastAPI application. LangChain + LangGraph primary framework."""
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import get_settings
from .models import (
    AnswerRequest, AnswerResponse,
    IngestRequest, IngestResponse, HealthResponse, SyncStatusResponse, DocumentInfo
)
from .ingestion import PDFIngestionService
from .vector_store import VectorStoreService
from .reasoning import ReasoningService
from .document_registry import DocumentRegistry
from .sync_service import DocumentSyncService
from .graph_lc import build_answer_graph, run_graph_until_route
from .graph_lc import nodes as graph_nodes
from .lc.chains import build_chains, astream_doc_only, astream_hybrid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global service instances
vector_store: VectorStoreService | None = None
ingestion_service: PDFIngestionService | None = None
reasoning_service: ReasoningService | None = None
document_registry: DocumentRegistry | None = None
sync_service: DocumentSyncService | None = None
answer_graph = None  # LangGraph compiled graph (built at startup)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global vector_store, ingestion_service, reasoning_service
    global document_registry, sync_service, answer_graph

    logger.info("Starting Agent service...")
    settings = get_settings()

    # Initialize services
    vector_store = VectorStoreService()
    ingestion_service = PDFIngestionService()
    reasoning_service = ReasoningService()

    # Initialize document registry and sync service
    registry_path = Path(settings.chroma_persist_directory) / "document_registry.json"
    document_registry = DocumentRegistry(registry_path)
    sync_service = DocumentSyncService(
        registry=document_registry,
        ingestion_service=ingestion_service,
        vector_store=vector_store
    )

    # Build LCEL chains and LangGraph workflow
    build_chains(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.1,
        max_tokens=2000,
    )
    answer_graph = build_answer_graph(
        reasoning_service=reasoning_service,
        settings=settings,
    )
    logger.info("LangChain LCEL chains and LangGraph workflow initialized")

    # Incremental sync on startup (idempotent)
    logger.info("Running incremental document sync...")
    result = sync_service.sync(delete_missing=False)

    if result.has_changes:
        logger.info(
            f"Sync result: {result.new_documents} new, "
            f"{result.updated_documents} updated, "
            f"{result.total_chunks_added} chunks added"
        )
    else:
        logger.info(f"No changes detected, {result.unchanged_documents} documents unchanged")

    if result.errors:
        for error in result.errors:
            logger.error(f"Sync error: {error}")

    logger.info("Agent service started successfully")

    yield

    logger.info("Shutting down Agent service...")


# Create FastAPI app
app = FastAPI(
    title="AICI Agent Service",
    description="Hybrid RAG Agent for planning document Q&A with session state",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _llm_available() -> bool:
    """Check if LLM is configured."""
    return bool(get_settings().openai_api_key)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        vector_store_ready=vector_store.is_ready() if vector_store else False,
        documents_count=vector_store.count() if vector_store else 0,
        registered_documents=len(document_registry.get_all_records()) if document_registry else 0
    )


@app.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """Get current document sync status."""
    if not sync_service:
        raise HTTPException(status_code=503, detail="Services not initialized")

    status = sync_service.get_status()
    return SyncStatusResponse(
        registered_documents=status["registered_documents"],
        total_chunks=status["total_chunks"],
        vector_store_count=status["vector_store_count"],
        documents=[
            DocumentInfo(
                source_id=doc["source_id"],
                version=doc["version"],
                chunk_count=doc["chunk_count"],
                page_count=doc["page_count"],
                last_ingested_at=doc["last_ingested_at"],
                content_hash=doc["content_hash"]
            )
            for doc in status["documents"]
        ]
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """Ingest PDF documents into the vector store (incremental sync)."""
    if not sync_service:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        if request.force_reingest:
            logger.info("Force reingest requested...")
            result = sync_service.force_reingest(source_id=request.source_id)
        else:
            logger.info("Running incremental sync...")
            result = sync_service.sync(delete_missing=request.delete_missing)

        total_docs = result.new_documents + result.updated_documents

        return IngestResponse(
            success=True,
            documents_processed=total_docs,
            chunks_created=result.total_chunks_added,
            message=(
                f"Sync complete: {result.new_documents} new, "
                f"{result.updated_documents} updated, "
                f"{result.unchanged_documents} unchanged, "
                f"{result.deleted_documents} deleted"
            )
        )

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_answer_graph(request: AnswerRequest) -> AnswerResponse:
    """Run LangGraph workflow and return AnswerResponse."""
    if not answer_graph:
        raise HTTPException(status_code=503, detail="Answer workflow not initialized")
    initial_state = {
        "question": request.question,
        "session_objects": request.session_objects,
    }
    final_state = answer_graph.invoke(initial_state)
    return AnswerResponse(
        answer=final_state.get("answer_text", ""),
        query_mode=final_state.get("query_mode"),
        session_summary=final_state.get("session_summary"),
    )


@app.post("/answer", response_model=AnswerResponse)
async def answer_question(request: AnswerRequest):
    """Answer a question using LangChain + LangGraph hybrid RAG."""
    if not vector_store or not reasoning_service:
        raise HTTPException(status_code=503, detail="Services not initialized")
    if not _llm_available():
        raise HTTPException(status_code=503, detail="LLM service not configured (missing API key)")
    try:
        return _run_answer_graph(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _state_to_done_payload(state: dict) -> dict:
    """Build NDJSON done payload from graph state."""
    session_summary = state.get("session_summary")
    if session_summary is not None and hasattr(session_summary, "model_dump"):
        session_summary = session_summary.model_dump()
    return {
        "t": "done",
        "answer": state.get("answer_text", ""),
        "query_mode": state.get("query_mode"),
        "session_summary": session_summary,
    }


async def _stream_answer_ndjson(request: AnswerRequest):
    """Async generator: run graph nodes until route, stream LLM via LCEL astream, then finalize. Single source of truth: graph_lc nodes."""
    if not vector_store or not reasoning_service:
        yield json.dumps({"t": "error", "message": "Services not initialized"}) + "\n"
        return
    if not _llm_available():
        yield json.dumps({"t": "error", "message": "LLM not configured"}) + "\n"
        return
    try:
        settings = get_settings()
        state = run_graph_until_route(request, reasoning_service, settings)

        # Guard path: finalize and emit chunk + done
        if state.get("guard_result"):
            state.update(graph_nodes.finalize_node(state))
            answer_text = state.get("answer_text", "")
            yield json.dumps({"t": "chunk", "c": answer_text}) + "\n"
            yield json.dumps(_state_to_done_payload(state)) + "\n"
            return

        # Main path: stream LLM, then finalize
        retrieved_docs = state.get("retrieved_docs", [])
        doc_only = state.get("doc_only", False)
        session_summary = state.get("session_summary")
        session_summary_dict = session_summary.model_dump() if session_summary else {}

        full_answer_chunks = []
        if doc_only:
            if not retrieved_docs:
                override_msg = "No explicit definition was found in the retrieved documents."
                state["answer_text"] = override_msg
                yield json.dumps({"t": "chunk", "c": override_msg}) + "\n"
            else:
                async for chunk in astream_doc_only(request.question, retrieved_docs):
                    full_answer_chunks.append(chunk)
                    yield json.dumps({"t": "chunk", "c": chunk}) + "\n"
                state["answer_text"] = "".join(full_answer_chunks)
        else:
            async for chunk in astream_hybrid(
                request.question,
                request.session_objects,
                session_summary_dict,
                retrieved_docs,
            ):
                full_answer_chunks.append(chunk)
                yield json.dumps({"t": "chunk", "c": chunk}) + "\n"
            state["answer_text"] = "".join(full_answer_chunks)

        state.update(graph_nodes.finalize_node(state))
        yield json.dumps(_state_to_done_payload(state)) + "\n"

    except Exception as e:
        logger.error(f"Error streaming answer: {e}")
        yield json.dumps({"t": "error", "message": str(e)}) + "\n"


@app.post("/answer/stream")
async def answer_question_stream(request: AnswerRequest):
    """
    Answer a question with streaming response.
    Returns NDJSON: {"t":"chunk","c":"..."} then {"t":"done", ...}.
    """
    if not vector_store or not reasoning_service:
        raise HTTPException(status_code=503, detail="Services not initialized")
    if not _llm_available():
        raise HTTPException(status_code=503, detail="LLM service not configured (missing API key)")
    return StreamingResponse(
        _stream_answer_ndjson(request),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AICI Agent Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": ["/health", "/sync/status", "/ingest", "/answer", "/answer/stream"],
        "features": [
            "Idempotent document ingestion with content hashing",
            "Incremental sync (NEW, UNCHANGED, UPDATED, DELETED)",
            "Hybrid RAG with LangChain + LangGraph (retrieval, LCEL chains, StateGraph)"
        ]
    }
