"""Pydantic models for Backend service."""
from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict
from typing import Any
import re


# ============== Configuration Constants ==============

# Limits for session objects
MAX_OBJECTS_COUNT = 1000
MAX_PAYLOAD_SIZE_KB = 512  # 512 KB max payload
MAX_STRING_LENGTH = 500
MAX_NESTING_DEPTH = 5


# ============== Error Response Models ==============

class ErrorDetail(BaseModel):
    """Detailed error information."""
    loc: list[str | int] = Field(
        default_factory=list,
        description="Location of the error (field path including array index)"
    )
    msg: str = Field(..., description="Human-readable error message")
    type: str = Field(..., description="Error type code")


class ErrorResponse(BaseModel):
    """Standardized error response format."""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="Field-level error details"
    )
    example: dict | None = Field(
        None,
        description="Example of expected format"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "Invalid drawing objects",
                "details": [
                    {"loc": ["objects", 0, "type"], "msg": "Field required", "type": "missing"}
                ],
                "example": {
                    "objects": [
                        {"type": "LINE", "layer": "Walls", "geometry": {"start": [0, 0], "end": [10, 10]}}
                    ]
                }
            }
        }
    )


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


# ============== Drawing Object Schema ==============

class DrawingObject(BaseModel):
    """
    A single drawing object with type, layer, and geometry.
    
    Required fields:
    - type: The object type (LINE, POLYLINE, POLYGON, POINT, etc.)
    - layer: The layer name this object belongs to
    
    Geometry is optional but recommended for spatial queries.
    Properties are optional additional attributes.
    """
    type: str = Field(
        ...,
        description="Object type (LINE, POLYLINE, POLYGON, POINT, CIRCLE, ARC, TEXT, BLOCK)"
    )
    layer: str = Field(
        ...,
        min_length=1,
        max_length=MAX_STRING_LENGTH,
        description="Layer name (e.g., 'Highway', 'Plot Boundary', 'Walls')"
    )
    geometry: dict[str, Any] | None = Field(
        None,
        description="Geometry data (structure depends on type)"
    )
    properties: dict[str, Any] | None = Field(
        None,
        description="Additional properties (name, color, material, etc.)"
    )

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        # Normalize to uppercase for comparison
        valid_types = {'LINE', 'POLYLINE', 'POLYGON', 'POINT', 'CIRCLE', 'ARC', 'TEXT', 'BLOCK'}
        if v.upper() not in valid_types:
            raise ValueError(
                f"Invalid type '{v}'. Must be one of: {', '.join(sorted(valid_types))}"
            )
        return v

    @field_validator('properties')
    @classmethod
    def validate_properties(cls, v):
        if v is not None:
            # Check for deeply nested structures
            def check_depth(obj, depth=0):
                if depth > MAX_NESTING_DEPTH:
                    raise ValueError(f'Properties nested too deeply (max {MAX_NESTING_DEPTH} levels)')
                if isinstance(obj, dict):
                    for val in obj.values():
                        check_depth(val, depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        check_depth(item, depth + 1)
            check_depth(v)
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "LINE",
                    "layer": "Walls",
                    "geometry": {"start": [0, 0], "end": [10, 10]},
                    "properties": {"material": "brick", "height": 2.4}
                },
                {
                    "type": "POLYGON",
                    "layer": "Plot Boundary",
                    "geometry": {"points": [[0, 0], [100, 0], [100, 50], [0, 50]]},
                    "properties": {"area": 5000}
                }
            ]
        }
    )


# ============== Session Models ==============

class SessionObjects(BaseModel):
    """
    Session drawing objects payload.
    
    Expected format:
    {
        "objects": [
            {"type": "LINE", "layer": "Walls", "geometry": {...}, "properties": {...}},
            {"type": "POLYGON", "layer": "Plot Boundary", "geometry": {...}}
        ]
    }
    
    Limits:
    - Maximum {MAX_OBJECTS_COUNT} objects per session
    - Each object must have 'type' and 'layer' fields
    """
    objects: list[DrawingObject] = Field(
        default_factory=list,
        max_length=MAX_OBJECTS_COUNT,
        description="List of drawing objects with type, layer, geometry, and properties"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "objects": [
                    {
                        "type": "LINE",
                        "layer": "Highway",
                        "geometry": {"start": [0, 0], "end": [100, 0]},
                        "properties": {"name": "Main Road", "width": 6}
                    },
                    {
                        "type": "POLYGON",
                        "layer": "Plot Boundary",
                        "geometry": {"points": [[10, 10], [90, 10], [90, 40], [10, 40]]},
                        "properties": {"area": 2400}
                    }
                ]
            }
        }
    )


class SessionObjectsResponse(BaseModel):
    """Response for session objects."""
    objects: list[dict[str, Any]]
    object_count: int
    layer_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Count of objects per layer"
    )
    validation_warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal validation warnings"
    )
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


# ============== Validation Helpers ==============

EXAMPLE_DRAWING_OBJECTS = {
    "objects": [
        {
            "type": "LINE",
            "layer": "Highway",
            "geometry": {"start": [0, 0], "end": [100, 0]},
            "properties": {"name": "Main Road", "width": 6}
        },
        {
            "type": "POLYGON",
            "layer": "Plot Boundary",
            "geometry": {"points": [[10, 10], [90, 10], [90, 40], [10, 40]]},
            "properties": {"area": 2400}
        },
        {
            "type": "POINT",
            "layer": "Doors",
            "geometry": {"position": [50, 20]},
            "properties": {"width": 0.9, "type": "entrance"}
        }
    ]
}
