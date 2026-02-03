"""Pydantic models for Backend service."""
from pydantic import (
    BaseModel, Field, EmailStr, field_validator, model_validator,
    ConfigDict, ValidationError
)
from typing import Any, Literal, Annotated, Union
from enum import Enum
import re


# ============== Configuration Constants ==============

# Limits for session objects
MAX_OBJECTS_COUNT = 1000
MAX_PAYLOAD_SIZE_KB = 512  # 512 KB max payload
MAX_STRING_LENGTH = 500
MAX_COORDINATES_PER_OBJECT = 10000
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


class ValidationErrorDetail(BaseModel):
    """Detailed validation error."""
    field: str
    message: str
    code: str | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error response with details."""
    detail: str
    errors: list[ValidationErrorDetail] = Field(default_factory=list)


# ============== Drawing Object Schema ==============

class ObjectType(str, Enum):
    """Valid drawing object types."""
    LINE = "LINE"
    POLYLINE = "POLYLINE"
    POLYGON = "POLYGON"
    POINT = "POINT"
    CIRCLE = "CIRCLE"
    ARC = "ARC"
    TEXT = "TEXT"
    BLOCK = "BLOCK"
    # Lowercase variants for flexibility
    line = "line"
    polyline = "polyline"
    polygon = "polygon"
    point = "point"
    circle = "circle"
    arc = "arc"
    text = "text"
    block = "block"


class Coordinate(BaseModel):
    """A 2D or 3D coordinate point."""
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    z: float | None = Field(None, description="Z coordinate (optional)")

    @field_validator('x', 'y', 'z')
    @classmethod
    def validate_coordinate(cls, v):
        if v is not None and (v < -1e10 or v > 1e10):
            raise ValueError('Coordinate value out of reasonable range')
        return v


class LineGeometry(BaseModel):
    """Geometry for LINE type objects."""
    start: list[float] | Coordinate = Field(..., description="Start point [x, y] or {x, y}")
    end: list[float] | Coordinate = Field(..., description="End point [x, y] or {x, y}")

    @field_validator('start', 'end')
    @classmethod
    def validate_point(cls, v):
        if isinstance(v, list):
            if len(v) < 2 or len(v) > 3:
                raise ValueError('Point must have 2 or 3 coordinates [x, y] or [x, y, z]')
            for coord in v:
                if not isinstance(coord, (int, float)):
                    raise ValueError('Coordinates must be numbers')
        return v


class PolylineGeometry(BaseModel):
    """Geometry for POLYLINE type objects."""
    points: list[list[float] | Coordinate] = Field(
        ..., 
        min_length=2,
        description="List of points forming the polyline"
    )

    @field_validator('points')
    @classmethod
    def validate_points(cls, v):
        if len(v) > MAX_COORDINATES_PER_OBJECT:
            raise ValueError(f'Too many points (max {MAX_COORDINATES_PER_OBJECT})')
        for i, point in enumerate(v):
            if isinstance(point, list):
                if len(point) < 2 or len(point) > 3:
                    raise ValueError(f'Point at index {i} must have 2 or 3 coordinates')
        return v


class PolygonGeometry(BaseModel):
    """Geometry for POLYGON type objects."""
    points: list[list[float] | Coordinate] = Field(
        ..., 
        min_length=3,
        description="List of points forming the polygon (min 3)"
    )
    
    @field_validator('points')
    @classmethod
    def validate_points(cls, v):
        if len(v) > MAX_COORDINATES_PER_OBJECT:
            raise ValueError(f'Too many points (max {MAX_COORDINATES_PER_OBJECT})')
        return v


class PointGeometry(BaseModel):
    """Geometry for POINT type objects."""
    position: list[float] | Coordinate = Field(..., description="Point position [x, y] or {x, y}")


class CircleGeometry(BaseModel):
    """Geometry for CIRCLE type objects."""
    center: list[float] | Coordinate = Field(..., description="Center point")
    radius: float = Field(..., gt=0, description="Circle radius")


class ArcGeometry(BaseModel):
    """Geometry for ARC type objects."""
    center: list[float] | Coordinate = Field(..., description="Arc center")
    radius: float = Field(..., gt=0, description="Arc radius")
    start_angle: float = Field(..., description="Start angle in degrees")
    end_angle: float = Field(..., description="End angle in degrees")


class TextGeometry(BaseModel):
    """Geometry for TEXT type objects."""
    position: list[float] | Coordinate = Field(..., description="Text insertion point")
    content: str = Field(..., max_length=MAX_STRING_LENGTH, description="Text content")
    height: float | None = Field(None, gt=0, description="Text height")
    rotation: float | None = Field(None, description="Rotation angle in degrees")


class ObjectProperties(BaseModel):
    """Common properties for drawing objects."""
    name: str | None = Field(None, max_length=MAX_STRING_LENGTH)
    color: str | int | None = None
    line_type: str | None = Field(None, alias="lineType")
    line_weight: float | None = Field(None, alias="lineWeight")
    material: str | None = Field(None, max_length=MAX_STRING_LENGTH)
    height: float | None = None
    width: float | None = None
    area: float | None = None
    length: float | None = None
    elevation: str | None = None
    classification: str | None = None
    
    model_config = ConfigDict(extra='allow', populate_by_name=True)


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

    @model_validator(mode='after')
    def validate_objects_count(self):
        if len(self.objects) > MAX_OBJECTS_COUNT:
            raise ValueError(
                f'Too many objects ({len(self.objects)}). Maximum allowed: {MAX_OBJECTS_COUNT}'
            )
        return self

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


def format_validation_errors(exc: ValidationError) -> ErrorResponse:
    """Convert Pydantic ValidationError to standardized ErrorResponse."""
    details = []
    for error in exc.errors():
        details.append(ErrorDetail(
            loc=list(error.get('loc', [])),
            msg=error.get('msg', 'Validation error'),
            type=error.get('type', 'value_error')
        ))
    
    return ErrorResponse(
        error="VALIDATION_ERROR",
        message="Invalid drawing objects. Please check the format and try again.",
        details=details,
        example=EXAMPLE_DRAWING_OBJECTS
    )
