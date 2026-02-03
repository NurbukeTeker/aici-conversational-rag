"""Pydantic models for Backend service."""
from pydantic import BaseModel, Field, EmailStr
from typing import Any


# ============== Auth Models ==============

class UserRegister(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    """User login request."""
    username: str
    password: str


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from JWT token."""
    username: str | None = None
    user_id: str | None = None


class UserResponse(BaseModel):
    """User info response (no password)."""
    user_id: str
    username: str
    email: str


# ============== Session Models ==============

class SessionObjects(BaseModel):
    """Session drawing objects."""
    objects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of drawing objects with layer, type, properties"
    )


class SessionObjectsResponse(BaseModel):
    """Response for session objects."""
    objects: list[dict[str, Any]]
    object_count: int
    updated_at: str | None = None


# ============== QA Models ==============

class QARequest(BaseModel):
    """Question-answer request."""
    question: str = Field(..., min_length=1, description="User question")


class ChunkEvidence(BaseModel):
    """Evidence from a document chunk."""
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
    """Combined evidence."""
    document_chunks: list[ChunkEvidence] = Field(default_factory=list)
    session_objects: ObjectEvidence | None = None


class SessionSummary(BaseModel):
    """Session summary from agent."""
    layer_counts: dict[str, int] = Field(default_factory=dict)
    plot_boundary_present: bool = False
    highways_present: bool = False
    total_objects: int = 0
    limitations: list[str] = Field(default_factory=list)


class QAResponse(BaseModel):
    """Question-answer response."""
    answer: str
    evidence: Evidence
    session_summary: SessionSummary | None = None


# ============== Health Models ==============

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    redis_connected: bool
    agent_available: bool
