"""Pydantic models for Agent service."""
from pydantic import BaseModel, Field
from typing import Any


class DrawingObject(BaseModel):
    """A single drawing object from the session JSON."""
    layer: str = Field(..., description="Layer name (e.g., Highway, Walls, Doors)")
    type: str = Field(default="unknown", description="Object type")
    properties: dict[str, Any] = Field(default_factory=dict, description="Object properties")


class SessionSummary(BaseModel):
    """Computed summary of session objects for reasoning."""
    layer_counts: dict[str, int] = Field(default_factory=dict)
    plot_boundary_present: bool = False
    highways_present: bool = False
    total_objects: int = 0
    limitations: list[str] = Field(default_factory=list)
    spatial_analysis: dict[str, Any] | None = Field(
        default=None,
        description="Spatial relationship analysis (property-highway fronting, distances, etc.)"
    )


class AnswerRequest(BaseModel):
    """Request model for /answer endpoint."""
    question: str = Field(..., description="User question")
    session_objects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Current session drawing objects (JSON)"
    )


class ChunkEvidence(BaseModel):
    """Evidence from a retrieved document chunk."""
    chunk_id: str
    source: str
    page: str | None = None
    section: str | None = None
    text_snippet: str


class ObjectEvidence(BaseModel):
    """Evidence from session objects."""
    layers_used: list[str]
    object_indices: list[int]


class Evidence(BaseModel):
    """Combined evidence for answer."""
    document_chunks: list[ChunkEvidence] = Field(default_factory=list)
    session_objects: ObjectEvidence | None = None


class AnswerResponse(BaseModel):
    """Response model for /answer endpoint."""
    answer: str
    evidence: Evidence
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