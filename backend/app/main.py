"""Backend service - FastAPI application."""
import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    UserRegister, UserResponse, Token,
    SessionObjects, SessionObjectsResponse,
    QARequest, QAResponse,
    HealthResponse, PasswordStrengthResponse, AvailabilityResponse,
    ValidationErrorDetail, ValidationErrorResponse
)
from .auth import create_access_token, get_current_user, TokenData
from .session import get_session_service, SessionService
from .database import get_database, get_db_session
from .user_service import (
    UserService, get_user_service,
    UserAlreadyExistsError, ValidationError as UserValidationError
)
from .validators import password_validator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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


# Create FastAPI app
app = FastAPI(
    title="AICI Backend Service",
    description="Authentication, Session Management, and QA Orchestration",
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

@app.put("/session/objects", response_model=SessionObjectsResponse)
async def update_session_objects(
    data: SessionObjects,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    session_service: Annotated[SessionService, Depends(get_session_service)]
):
    """Update session drawing objects."""
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )
    
    success = session_service.set_objects(current_user.user_id, data.objects)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store session objects"
        )
    
    objects, meta = session_service.get_objects(current_user.user_id)
    
    return SessionObjectsResponse(
        objects=objects,
        object_count=len(objects),
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
    
    return SessionObjectsResponse(
        objects=objects,
        object_count=len(objects),
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
            "/health"
        ]
    }
