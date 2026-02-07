"""Agent service - FastAPI application."""
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import get_settings
from .models import (
    AnswerRequest, AnswerResponse, Evidence, ChunkEvidence, ObjectEvidence,
    IngestRequest, IngestResponse, HealthResponse, SyncStatusResponse, DocumentInfo
)
from .ingestion import PDFIngestionService
from .vector_store import VectorStoreService
from .reasoning import ReasoningService
from .llm_service import LLMService
from .document_registry import DocumentRegistry
from .sync_service import DocumentSyncService

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
llm_service: LLMService | None = None
document_registry: DocumentRegistry | None = None
sync_service: DocumentSyncService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global vector_store, ingestion_service, reasoning_service, llm_service
    global document_registry, sync_service
    
    logger.info("Starting Agent service...")
    settings = get_settings()
    
    # Initialize services
    vector_store = VectorStoreService()
    ingestion_service = PDFIngestionService()
    reasoning_service = ReasoningService()
    llm_service = LLMService()
    
    # Initialize document registry and sync service
    registry_path = Path(settings.chroma_persist_directory) / "document_registry.json"
    document_registry = DocumentRegistry(registry_path)
    sync_service = DocumentSyncService(
        registry=document_registry,
        ingestion_service=ingestion_service,
        vector_store=vector_store
    )
    
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


@app.post("/answer", response_model=AnswerResponse)
async def answer_question(request: AnswerRequest):
    """Answer a question using hybrid RAG."""
    if not vector_store or not reasoning_service or not llm_service:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    if not llm_service.is_available():
        raise HTTPException(status_code=503, detail="LLM service not configured (missing API key)")
    
    try:
        # Validate session JSON
        warnings = reasoning_service.validate_json_schema(request.session_objects)
        if warnings:
            logger.warning(f"JSON validation warnings: {warnings}")
        
        # Compute session summary
        session_summary = reasoning_service.compute_session_summary(request.session_objects)
        logger.info(f"Session summary: {session_summary.layer_counts}")
        
        # Retrieve relevant chunks
        settings = get_settings()
        retrieved_chunks = vector_store.search(
            query=request.question,
            top_k=settings.retrieval_top_k
        )
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks")
        
        # Generate answer
        answer = llm_service.generate_answer(
            question=request.question,
            session_objects=request.session_objects,
            session_summary=session_summary.model_dump(),
            retrieved_chunks=retrieved_chunks
        )
        
        # Extract layers used for evidence
        layers_used, indices_used = reasoning_service.extract_layers_used(
            request.session_objects,
            request.question
        )
        
        # Build evidence
        chunk_evidence = [
            ChunkEvidence(
                chunk_id=chunk["id"],
                source=chunk["source"],
                page=chunk.get("page"),
                section=chunk.get("section"),
                text_snippet=chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"]
            )
            for chunk in retrieved_chunks
        ]
        
        object_evidence = ObjectEvidence(
            layers_used=list(set(layers_used)),
            object_indices=indices_used
        ) if layers_used else None
        
        return AnswerResponse(
            answer=answer,
            evidence=Evidence(
                document_chunks=chunk_evidence,
                session_objects=object_evidence
            ),
            session_summary=session_summary
        )
        
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _stream_answer_ndjson(request: AnswerRequest):
    """Async generator yielding NDJSON lines for streaming response."""
    if not vector_store or not reasoning_service or not llm_service:
        yield json.dumps({"t": "error", "message": "Services not initialized"}) + "\n"
        return
    if not llm_service.is_available():
        yield json.dumps({"t": "error", "message": "LLM not configured"}) + "\n"
        return
    try:
        warnings = reasoning_service.validate_json_schema(request.session_objects)
        if warnings:
            logger.warning(f"JSON validation warnings: {warnings}")
        session_summary = reasoning_service.compute_session_summary(request.session_objects)
        settings = get_settings()
        retrieved_chunks = vector_store.search(
            query=request.question,
            top_k=settings.retrieval_top_k
        )
        full_answer_chunks = []
        async for chunk in llm_service.generate_answer_stream_async(
            question=request.question,
            session_objects=request.session_objects,
            session_summary=session_summary.model_dump(),
            retrieved_chunks=retrieved_chunks
        ):
            full_answer_chunks.append(chunk)
            yield json.dumps({"t": "chunk", "c": chunk}) + "\n"
        full_answer = "".join(full_answer_chunks)
        layers_used, indices_used = reasoning_service.extract_layers_used(
            request.session_objects,
            request.question
        )
        chunk_evidence = [
            {
                "chunk_id": c["id"],
                "source": c["source"],
                "page": c.get("page"),
                "section": c.get("section"),
                "text_snippet": (c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"]),
            }
            for c in retrieved_chunks
        ]
        object_evidence = (
            {"layers_used": list(set(layers_used)), "object_indices": indices_used}
            if layers_used else None
        )
        done_payload = {
            "t": "done",
            "answer": full_answer,
            "evidence": {
                "document_chunks": chunk_evidence,
                "session_objects": object_evidence,
            },
            "session_summary": session_summary.model_dump(),
        }
        yield json.dumps(done_payload) + "\n"
    except Exception as e:
        logger.error(f"Error streaming answer: {e}")
        yield json.dumps({"t": "error", "message": str(e)}) + "\n"


@app.post("/answer/stream")
async def answer_question_stream(request: AnswerRequest):
    """
    Answer a question using hybrid RAG with streaming response.
    Returns NDJSON stream: lines of {"t":"chunk","c":"..."} then {"t":"done", ...}.
    """
    if not vector_store or not reasoning_service or not llm_service:
        raise HTTPException(status_code=503, detail="Services not initialized")
    if not llm_service.is_available():
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
            "Hybrid RAG with persistent knowledge + ephemeral session"
        ]
    }
