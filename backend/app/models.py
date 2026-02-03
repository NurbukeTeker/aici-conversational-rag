"""Pydantic models for Backend service."""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Any
import re


# ============== Auth Models ==============

class UserRegister(BaseModel):
    """User registration request with validation."""
    username: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Username (3-30 chars, alphanumeric and underscore)"
    )
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8+ chars with uppercase, lowercase, digit, special)"
    )
    display_name: str | None = Field(
        None,
        max_length=100,
        description="Display name (optional)"
    )
    
    @field_validator('username')
    @classmethod
    def validate_username_format(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError(
                'Username must start with a letter and contain only letters, numbers, and underscores'
            )
        if '__' in v:
            raise ValueError('Username cannot contain consecutive underscores')
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password_basic(cls, v: str) -> str:
        """Basic password validation (detailed validation in backend)."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserLogin(BaseModel):
    """User login request."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=3600, description="Token expiry in seconds")


class TokenData(BaseModel):
    """Data extracted from JWT token."""
    username: str | None = None
    user_id: str | None = None


class UserResponse(BaseModel):
    """User info response (no password)."""
    user_id: str
    username: str
    email: str
    display_name: str | None = None
    is_active: bool = True
    is_verified: bool = False
    created_at: str | None = None


class PasswordStrengthResponse(BaseModel):
    """Password strength check response."""
    is_valid: bool
    score: int = Field(ge=0, le=100, description="Strength score 0-100")
    strength: str = Field(description="Very Weak, Weak, Fair, Strong, Very Strong")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AvailabilityResponse(BaseModel):
    """Username/Email availability check response."""
    available: bool
    message: str | None = None


class ValidationErrorDetail(BaseModel):
    """Detailed validation error."""
    field: str
    message: str
    code: str | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error response with details."""
    detail: str
    errors: list[ValidationErrorDetail] = Field(default_factory=list)


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
