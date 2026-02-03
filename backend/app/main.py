"""Backend service - FastAPI application."""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from .config import get_settings
from .models import (
    UserRegister, UserResponse, Token,
    SessionObjects, SessionObjectsResponse,
    QARequest, QAResponse,
    HealthResponse
)
from .auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, TokenData
)
from .session import get_session_service, get_user_store, SessionService, UserStore

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
    get_user_store()
    
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
    user_store: Annotated[UserStore, Depends(get_user_store)]
):
    """Register a new user."""
    try:
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user_data.password)
        
        user = user_store.create_user(
            user_id=user_id,
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password
        )
        
        logger.info(f"User registered: {user_data.username}")
        
        return UserResponse(
            user_id=user["user_id"],
            username=user["username"],
            email=user["email"]
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/auth/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_store: Annotated[UserStore, Depends(get_user_store)]
):
    """Login and get JWT token."""
    user = user_store.get_user(form_data.username)
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["user_id"]}
    )
    
    logger.info(f"User logged in: {user['username']}")
    
    return Token(access_token=access_token)


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
        "endpoints": ["/auth/register", "/auth/login", "/session/objects", "/qa", "/health"]
    }
