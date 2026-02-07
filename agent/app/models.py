"""Pydantic models for Agent service."""
from pydantic import BaseModel, Field
from typing import Any, Literal


class SessionSummary(BaseModel):
    """Computed summary of session objects for reasoning."""
    layer_counts: dict[str, int] = Field(default_factory=dict)
    plot_boundary_present: bool = False
    highways_present: bool = False
    total_objects: int = 0
    limitations: list[str] = Field(default_factory=list)


class AnswerRequest(BaseModel):
    """Request model for /answer endpoint."""
    question: str = Field(..., description="User question")
    session_objects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Current session drawing objects (JSON)"
    )


class AnswerResponse(BaseModel):
    """Response model for /answer endpoint."""
    answer: str
    query_mode: Literal["doc_only", "json_only", "hybrid"] | None = Field(default=None, description="From routing")
    session_summary: SessionSummary | None = None


class IngestRequest(BaseModel):
    """Request model for /ingest endpoint."""
    force_reingest: bool = Field(
        default=False,
        description="Force re-ingestion (clears registry and re-processes all)"
    )
    delete_missing: bool = Field(
        default=False,
        description="Delete chunks for documents no longer in source directory"
    )
    source_id: str | None = Field(
        default=None,
        description="Specific document to re-ingest (with force_reingest)"
    )


class IngestResponse(BaseModel):
    """Response model for /ingest endpoint."""
    success: bool
    documents_processed: int
    chunks_created: int
    message: str


class DocumentInfo(BaseModel):
    """Information about a registered document."""
    source_id: str
    version: int
    chunk_count: int
    page_count: int
    last_ingested_at: str
    content_hash: str


class SyncStatusResponse(BaseModel):
    """Response model for /sync/status endpoint."""
    registered_documents: int
    total_chunks: int
    vector_store_count: int
    documents: list[DocumentInfo]


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str
    vector_store_ready: bool
    documents_count: int
    registered_documents: int = 0