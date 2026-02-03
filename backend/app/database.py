"""Database configuration and models using SQLAlchemy."""
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Index
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import get_settings

logger = logging.getLogger(__name__)

# Create declarative base
Base = declarative_base()


class User(Base):
    """User database model."""
    __tablename__ = "users"
    
    # Primary key
    id = Column(String(36), primary_key=True)  # UUID
    
    # Unique identifiers
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    
    # Credentials (hashed)
    hashed_password = Column(String(255), nullable=False)
    
    # Profile
    display_name = Column(String(100), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), 
                       onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    
    # Indexes for faster lookups
    __table_args__ = (
        Index('ix_users_email_lower', 'email'),
        Index('ix_users_username_lower', 'username'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary (without password)."""
        return {
            "user_id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class DatabaseService:
    """Service for database operations."""
    
    def __init__(self):
        settings = get_settings()
        
        # Ensure data directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create engine
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},  # SQLite specific
            echo=settings.database_echo
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        # Create tables
        Base.metadata.create_all(bind=self.engine)
        logger.info(f"Database initialized at {settings.database_url}")
    
    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()


# Global database service instance
_db_service: DatabaseService | None = None


def get_database() -> DatabaseService:
    """Get the database service instance."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service


def get_db_session():
    """Dependency for getting a database session."""
    db = get_database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
