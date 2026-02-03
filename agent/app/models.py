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
        description="Force re-ingestion even if documents exist"
    )


class IngestResponse(BaseModel):
    """Response model for /ingest endpoint."""
    success: bool
    documents_processed: int
    chunks_created: int
    message: str


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str
    vector_store_ready: bool
    documents_count: int
