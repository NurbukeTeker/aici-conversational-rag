"""Backend service - FastAPI application."""
import json
import logging
from collections import Counter
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Depends, status, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    UserRegister, UserResponse, Token,
    SessionObjects, SessionObjectsResponse,
    QARequest, QAResponse,
    HealthResponse, PasswordStrengthResponse, AvailabilityResponse,
    ErrorResponse, ExportRequest,
    MAX_PAYLOAD_SIZE_KB, MAX_OBJECTS_COUNT, EXAMPLE_DRAWING_OBJECTS
)
from .auth import create_access_token, get_current_user, decode_token, TokenData
from .session import get_session_service, SessionService
from .database import get_database, get_db_session
from .user_service import (
    UserService, get_user_service,
    UserAlreadyExistsError, ValidationError as UserValidationError
)
from .validators import password_validator
from .export_service import get_export_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============== Custom Exception Handlers ==============

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with field-level details."""
    details = []
    for error in exc.errors():
        msg = error.get("msg", "Validation error")
        err_type = error.get("type", "value_error")
        # Make "extra keys" errors clear as key error for session objects
        if err_type == "extra_forbidden":
            loc = list(error.get("loc", []))
            if "objects" in str(loc) and len(loc) > 0:
                invalid_key = loc[-1] if isinstance(loc[-1], str) else None
                if invalid_key:
                    msg = (
                        f"Invalid key '{invalid_key}' in drawing object. "
                        "Allowed keys only: type, layer, geometry, properties."
                    )
                else:
                    msg = (
                        "Invalid key(s) in drawing object. "
                        "Allowed keys only: type, layer, geometry, properties."
                    )
        details.append({
            "loc": list(error.get("loc", [])),
            "msg": msg,
            "type": err_type
        })
    
    # Check if this is about session objects
    is_session_error = any("objects" in str(d.get("loc", [])) for d in details)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Invalid request data. Please check the format and try again.",
            "detail": details,  # Frontend normalizeDetail() uses this to show msg(s)
            "details": details,
            "example": EXAMPLE_DRAWING_OBJECTS if is_session_error else None
        }
    )


async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError):
    """Handle JSON parsing errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "INVALID_JSON",
            "message": "Invalid JSON. Expected an array of drawing objects.",
            "details": [{
                "loc": [],
                "msg": f"JSON parse error at position {exc.pos}: {exc.msg}",
                "type": "json_invalid"
            }],
            "example": EXAMPLE_DRAWING_OBJECTS
        }
    )


# ============== Request Size Limiter ==============

class RequestSizeLimitMiddleware:
    """Middleware to limit request body size."""
    
    def __init__(self, app, max_size_kb: int = MAX_PAYLOAD_SIZE_KB):
        self.app = app
        self.max_size_bytes = max_size_kb * 1024
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        content_length = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"content-length":
                try:
                    content_length = int(header_value.decode())
                except (ValueError, UnicodeDecodeError):
                    pass
                break
        
        # Check Content-Length header
        if content_length is not None and content_length > self.max_size_bytes:
            response = JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": "PAYLOAD_TOO_LARGE",
                    "message": f"Request payload too large. Maximum allowed: {MAX_PAYLOAD_SIZE_KB} KB",
                    "details": [{
                        "loc": [],
                        "msg": f"Payload size ({content_length // 1024} KB) exceeds limit ({MAX_PAYLOAD_SIZE_KB} KB)",
                        "type": "payload_too_large"
                    }],
                    "example": None
                }
            )
            await response(scope, receive, send)
            return
        
        await self.app(scope, receive, send)


# ============== Application Lifecycle ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Backend service...")
    
    # Initialize services
    get_session_service()
    get_database()  # Initialize database
    
    logger.info("Backend service started successfully")
    
    yield
    
    logger.info("Shutting down Backend service...")


# ============== Create FastAPI App ==============

app = FastAPI(
    title="AICI Backend Service",
    description="Authentication, Session Management, and QA Orchestration",
    version="1.0.0",
    lifespan=lifespan
)

# Add request size limiter
app.add_middleware(RequestSizeLimitMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(json.JSONDecodeError, json_decode_exception_handler)


# ============== Helper Functions ==============

def compute_layer_summary(objects: list[dict]) -> dict[str, int]:
    """Compute count of objects per layer."""
    layers = []
    for obj in objects:
        layer = obj.get("layer") or obj.get("Layer") or "Unknown"
        layers.append(layer)
    return dict(Counter(layers))


def validate_objects_warnings(objects: list[dict]) -> list[str]:
    """Check for non-fatal issues and return warnings."""
    warnings = []
    
    if not objects:
        warnings.append("No objects provided. Q&A will use only document knowledge.")
    
    # Check for objects missing geometry
    objects_without_geometry = sum(1 for obj in objects if not obj.get("geometry"))
    if objects_without_geometry > 0:
        warnings.append(
            f"{objects_without_geometry} object(s) have no geometry data. "
            "Spatial queries may be limited."
        )
    
    # Check for common layer types
    layers = {(obj.get("layer") or "").lower() for obj in objects}
    if not any("boundary" in l or "plot" in l for l in layers):
        warnings.append("No 'Plot Boundary' layer detected.")
    
    return warnings


# ============== Auth Endpoints ==============

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: Annotated[Session, Depends(get_db_session)]
):
    """
    Register a new user.
    
    Validates:
    - Username format and uniqueness
    - Email format and uniqueness
    - Password strength
    """
    user_service = get_user_service(db)
    
    try:
        user = user_service.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.display_name
        )
        
        logger.info(f"User registered: {user_data.username}")
        
        return UserResponse(
            user_id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at.isoformat() if user.created_at else None
        )
        
    except UserAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with this {e.field} already exists"
        )
    except UserValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(e.errors)
        )


@app.post("/auth/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db_session)]
):
    """
    Login and get JWT token.
    
    Accepts username or email in the username field.
    """
    user_service = get_user_service(db)
    settings = get_settings()
    
    user = user_service.authenticate(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )
    
    logger.info(f"User logged in: {user.username}")
    
    return Token(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)]
):
    """Get current authenticated user info."""
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_service = get_user_service(db)
    user = user_service.get_by_id(current_user.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at.isoformat() if user.created_at else None
    )


# ============== Validation Endpoints ==============

@app.get("/auth/check-username", response_model=AvailabilityResponse)
async def check_username_availability(
    username: Annotated[str, Query(min_length=1, max_length=30)],
    db: Annotated[Session, Depends(get_db_session)]
):
    """Check if a username is available."""
    user_service = get_user_service(db)
    available, message = user_service.check_username_available(username)
    
    return AvailabilityResponse(
        available=available,
        message=message
    )


@app.get("/auth/check-email", response_model=AvailabilityResponse)
async def check_email_availability(
    email: Annotated[str, Query(min_length=1, max_length=255)],
    db: Annotated[Session, Depends(get_db_session)]
):
    """Check if an email is available."""
    user_service = get_user_service(db)
    available, message = user_service.check_email_available(email)
    
    return AvailabilityResponse(
        available=available,
        message=message
    )


@app.post("/auth/check-password", response_model=PasswordStrengthResponse)
async def check_password_strength(
    password: str
):
    """
    Check password strength without storing.
    
    Returns validation errors, warnings, and strength score.
    """
    result = password_validator.validate(password)
    score, strength = password_validator.get_strength(password)
    
    return PasswordStrengthResponse(
        is_valid=result.is_valid,
        score=score,
        strength=strength,
        errors=result.errors,
        warnings=result.warnings
    )


# ============== Session Endpoints ==============

@app.put(
    "/session/objects",
    response_model=SessionObjectsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid JSON"},
        413: {"model": ErrorResponse, "description": "Payload too large"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    }
)
async def update_session_objects(
    data: SessionObjects,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """
    Update session drawing objects.
    
    **Accepts:**
    - `application/json` content type
    - A JSON object with an `objects` array
    
    **Object Schema:**
    Each object must have:
    - `type`: Object type (LINE, POLYLINE, POLYGON, POINT, CIRCLE, ARC, TEXT, BLOCK)
    - `layer`: Layer name (e.g., "Highway", "Plot Boundary", "Walls")
    
    Optional fields:
    - `geometry`: Geometry data (structure depends on type)
    - `properties`: Additional attributes (name, color, material, etc.)
    
    **Limits:**
    - Maximum {max_objects} objects
    - Maximum {max_size} KB payload size
    
    **Example:**
    ```json
    {{
        "objects": [
            {{
                "type": "LINE",
                "layer": "Highway",
                "geometry": {{"start": [0, 0], "end": [100, 0]}},
                "properties": {{"name": "Main Road", "width": 6}}
            }}
        ]
    }}
    ```
    """.format(max_objects=MAX_OBJECTS_COUNT, max_size=MAX_PAYLOAD_SIZE_KB)
    
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    # Convert DrawingObject instances to dicts for storage
    objects_list = [obj.model_dump() for obj in data.objects]
    
    # Normalize geometry formats (points/start-end → GeoJSON coordinates)
    from .geometry_normalizer import normalize_session_objects
    objects_list = normalize_session_objects(objects_list)
    
    # Store objects
    success = session_service.set_objects(current_user.user_id, objects_list)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store session objects"
        )
    
    # Retrieve stored objects
    objects, meta = session_service.get_objects(current_user.user_id)
    
    # Compute summaries
    layer_summary = compute_layer_summary(objects)
    warnings = validate_objects_warnings(objects)
    
    logger.info(f"Session updated for user {current_user.user_id}: {len(objects)} objects, layers: {layer_summary}")
    
    return SessionObjectsResponse(
        objects=objects,
        object_count=len(objects),
        layer_summary=layer_summary,
        validation_warnings=warnings,
        updated_at=meta.get("updated_at") if meta else None
    )


@app.get("/session/objects", response_model=SessionObjectsResponse)
async def get_session_objects(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """Get current session drawing objects."""
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    objects, meta = session_service.get_objects(current_user.user_id)
    
    # Compute summaries
    layer_summary = compute_layer_summary(objects)
    warnings = validate_objects_warnings(objects)
    
    return SessionObjectsResponse(
        objects=objects,
        object_count=len(objects),
        layer_summary=layer_summary,
        validation_warnings=warnings,
        updated_at=meta.get("updated_at") if meta else None
    )


# ============== QA Endpoint ==============

@app.post("/qa", response_model=QAResponse)
async def ask_question(
    data: QARequest,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """Ask a question using hybrid RAG."""
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    settings = get_settings()
    
    # Get current session objects
    session_objects, _ = session_service.get_objects(current_user.user_id)
    
    # Normalize geometry formats before sending to agent (ensures geometry guard compatibility)
    from .geometry_normalizer import normalize_session_objects
    session_objects = normalize_session_objects(session_objects)
    
    # Call agent service
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.agent_service_url}/answer",
                json={
                    "question": data.question,
                    "session_objects": session_objects
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Agent service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Agent service error: {response.text}"
                )
            
            agent_response = response.json()
            return QAResponse(**agent_response)
            
    except httpx.RequestError as e:
        logger.error(f"Error calling agent service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service unavailable"
        )


# ============== WebSocket (Real-time Q&A Streaming) ==============

@app.websocket("/ws/qa")
async def websocket_qa(websocket: WebSocket):
    """
    Real-time Q&A over WebSocket.
    Auth via first message (avoids token in URL/logs): send {"type": "auth", "token": "<jwt>"} once, then {"question": "..."}.
    Receive NDJSON stream: {"t":"chunk","c":"..."} then {"t":"done",...}.
    """
    await websocket.accept()
    # First message must be auth (token not in URL so it does not appear in access logs)
    try:
        raw = await websocket.receive_text()
        data = json.loads(raw)
        if data.get("type") != "auth":
            await websocket.send_json({"t": "error", "message": "First message must be {\"type\": \"auth\", \"token\": \"<jwt>\"}"})
            await websocket.close(code=4001)
            return
        token = data.get("token") or ""
        if not token:
            await websocket.send_json({"t": "error", "message": "Missing token in auth message"})
            await websocket.close(code=4001)
            return
        token_data = decode_token(token)
        if not token_data.user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    session_service = get_session_service()
    settings = get_settings()

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                question = (data.get("question") or "").strip()
                if not question:
                    await websocket.send_json({"t": "error", "message": "Missing or empty question"})
                    continue

                session_objects, _ = session_service.get_objects(token_data.user_id)
                # Normalize geometry formats before sending to agent
                from .geometry_normalizer import normalize_session_objects
                session_objects = normalize_session_objects(session_objects)
                stream_url = f"{settings.agent_service_url}/answer/stream"
                async with httpx.AsyncClient(timeout=60.0) as client:
                    async with client.stream(
                        "POST",
                        stream_url,
                        json={"question": question, "session_objects": session_objects},
                    ) as response:
                        if response.status_code != 200:
                            await websocket.send_json({
                                "t": "error",
                                "message": f"Agent error: {response.status_code}"
                            })
                            continue
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                await websocket.send_json(obj)
                                if obj.get("t") == "done":
                                    break
                                if obj.get("t") == "error":
                                    break
                            except json.JSONDecodeError:
                                pass
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.exception("WebSocket qa error")
                try:
                    await websocket.send_json({"t": "error", "message": str(e)})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ============== Health Endpoint ==============

@app.get("/health", response_model=HealthResponse)
async def health_check(
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """Health check endpoint."""
    settings = get_settings()
    
    # Check Redis
    redis_connected = session_service.is_connected()
    
    # Check Agent service
    agent_available = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.agent_service_url}/health")
            agent_available = response.status_code == 200
    except Exception:
        pass
    
    return HealthResponse(
        status="healthy" if redis_connected else "degraded",
        redis_connected=redis_connected,
        agent_available=agent_available
    )


# ============== Export Endpoints ==============

@app.post("/export/json")
async def download_dialogue_json(
    data: ExportRequest,
    current_user: Annotated[TokenData, Depends(get_current_user)]
):
    """
    Download Q&A dialogues as JSON file.
    
    Returns a JSON file with all dialogues and evidence.
    """
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    # Convert dialogues to dict format
    dialogues = [d.model_dump() for d in data.dialogues]
    
    # Build export data
    from datetime import datetime
    export_data = {
        "export_info": {
            "exported_at": datetime.now().isoformat(),
            "exported_by": current_user.username or "user",
            "total_dialogues": len(dialogues)
        },
        "session_summary": data.session_summary,
        "dialogues": dialogues
    }
    
    # Generate filename
    filename = f"AICI_QA_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    logger.info(f"User {current_user.user_id} downloaded JSON export with {len(dialogues)} items")
    
    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.post("/export/csv")
async def download_dialogue_csv(
    request: Request,
    current_user: Annotated[TokenData, Depends(get_current_user)]
):
    """
    Download Q&A dialogues as CSV file.
    
    Accepts JSON body with dialogues array and optional session_summary.
    Returns a CSV file with all dialogues and evidence.
    """
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {str(e)}"
        )
    
    dialogues_raw = body.get("dialogues", [])
    if not isinstance(dialogues_raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dialogues must be an array"
        )
    
    if len(dialogues_raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dialogues array cannot be empty"
        )
    
    # Convert to dict format (handle plain dicts from frontend)
    dialogues = []
    for d in dialogues_raw:
        if isinstance(d, dict):
            dialogues.append({
                "question": d.get("question", ""),
                "answer": d.get("answer", ""),
                "evidence": d.get("evidence"),
                "timestamp": d.get("timestamp")
            })
        elif hasattr(d, 'model_dump'):
            dialogues.append(d.model_dump())
        else:
            dialogues.append({
                "question": getattr(d, 'question', ''),
                "answer": getattr(d, 'answer', ''),
                "evidence": getattr(d, 'evidence', None),
                "timestamp": getattr(d, 'timestamp', None)
            })
    
    export_service = get_export_service()
    session_summary = body.get("session_summary")
    
    # Generate CSV
    csv_bytes = export_service.create_dialogue_csv(
        dialogues=dialogues,
        username=current_user.username or "user",
        session_summary=session_summary
    )
    
    # Generate filename
    from datetime import datetime
    filename = f"AICI_QA_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    logger.info(f"User {current_user.user_id} downloaded CSV export with {len(dialogues)} items")
    
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AICI Backend Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "/auth/register",
            "/auth/login",
            "/auth/me",
            "/auth/check-username",
            "/auth/check-email",
            "/auth/check-password",
            "/session/objects",
            "/qa",
            "/ws/qa",
            "/export/csv",
            "/export/json",
            "/health"
        ],
        "limits": {
            "max_objects": MAX_OBJECTS_COUNT,
            "max_payload_kb": MAX_PAYLOAD_SIZE_KB
        }
    }
