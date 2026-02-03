"""Agent service - FastAPI application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import (
    AnswerRequest, AnswerResponse, Evidence, ChunkEvidence, ObjectEvidence,
    IngestRequest, IngestResponse, HealthResponse
)
from .ingestion import PDFIngestionService
from .vector_store import VectorStoreService
from .reasoning import ReasoningService
from .llm_service import LLMService

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global vector_store, ingestion_service, reasoning_service, llm_service
    
    logger.info("Starting Agent service...")
    
    # Initialize services
    vector_store = VectorStoreService()
    ingestion_service = PDFIngestionService()
    reasoning_service = ReasoningService()
    llm_service = LLMService()
    
    # Auto-ingest if vector store is empty
    if not vector_store.is_ready():
        logger.info("Vector store is empty, auto-ingesting PDFs...")
        chunks = ingestion_service.get_chunks_for_storage()
        if chunks:
            vector_store.add_documents(chunks)
            logger.info(f"Auto-ingested {len(chunks)} chunks")
        else:
            logger.warning("No PDF documents found for ingestion")
    
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
        documents_count=vector_store.count() if vector_store else 0
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """Ingest PDF documents into the vector store."""
    if not ingestion_service or not vector_store:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    try:
        # Clear if force reingest
        if request.force_reingest:
            logger.info("Force reingest requested, clearing vector store...")
            vector_store.clear()
        
        # Get chunks
        chunks = ingestion_service.get_chunks_for_storage()
        
        if not chunks:
            return IngestResponse(
                success=True,
                documents_processed=0,
                chunks_created=0,
                message="No PDF documents found in data directory"
            )
        
        # Count unique sources
        sources = set(c["metadata"]["source"] for c in chunks)
        
        # Add to vector store
        vector_store.add_documents(chunks)
        
        return IngestResponse(
            success=True,
            documents_processed=len(sources),
            chunks_created=len(chunks),
            message=f"Successfully ingested {len(sources)} documents into {len(chunks)} chunks"
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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AICI Agent Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": ["/health", "/ingest", "/answer"]
    }
