"""User service with database persistence."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .database import User
from .auth import get_password_hash, verify_password
from .validators import (
    password_validator, username_validator, email_validator,
    ValidationResult
)

logger = logging.getLogger(__name__)


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user that already exists."""
    def __init__(self, field: str, value: str):
        self.field = field
        self.value = value
        super().__init__(f"User with {field} '{value}' already exists")


class UserNotFoundError(Exception):
    """Raised when a user is not found."""
    pass


class ValidationError(Exception):
    """Raised when validation fails."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class UserService:
    """Service for user CRUD operations with validation."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        display_name: Optional[str] = None
    ) -> User:
        """
        Create a new user with full validation.
        
        Raises:
            ValidationError: If any field fails validation
            UserAlreadyExistsError: If username or email already exists
        """
        # Normalize inputs
        username = username.strip()
        email = email_validator.normalize(email)
        
        # Validate username
        username_result = username_validator.validate(username)
        if not username_result.is_valid:
            raise ValidationError(username_result.errors)
        
        # Validate email
        email_result = email_validator.validate(email)
        if not email_result.is_valid:
            raise ValidationError(email_result.errors)
        
        # Validate password
        password_result = password_validator.validate(password)
        if not password_result.is_valid:
            raise ValidationError(password_result.errors)
        
        # Check for existing user with same username
        existing = self.db.query(User).filter(
            User.username.ilike(username)
        ).first()
        if existing:
            raise UserAlreadyExistsError("username", username)
        
        # Check for existing user with same email
        existing = self.db.query(User).filter(
            User.email.ilike(email)
        ).first()
        if existing:
            raise UserAlreadyExistsError("email", email)
        
        # Create user
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            display_name=display_name or username,
            is_active=True,
            is_verified=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"Created user: {username} ({email})")
            return user
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Database integrity error creating user: {e}")
            # Try to identify which field caused the conflict
            if "username" in str(e).lower():
                raise UserAlreadyExistsError("username", username)
            elif "email" in str(e).lower():
                raise UserAlreadyExistsError("email", email)
            raise
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username (case-insensitive)."""
        return self.db.query(User).filter(
            User.username.ilike(username)
        ).first()
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email (case-insensitive)."""
        email = email_validator.normalize(email)
        return self.db.query(User).filter(
            User.email.ilike(email)
        ).first()
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def authenticate(self, username_or_email: str, password: str) -> Optional[User]:
        """
        Authenticate user by username or email.
        
        Returns:
            User if authentication succeeds, None otherwise
        """
        # Try username first
        user = self.get_by_username(username_or_email)
        
        # If not found by username, try email
        if not user:
            user = self.get_by_email(username_or_email)
        
        if not user:
            logger.warning(f"Authentication failed: user not found ({username_or_email})")
            return None
        
        if not user.is_active:
            logger.warning(f"Authentication failed: user inactive ({username_or_email})")
            return None
        
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: invalid password ({username_or_email})")
            return None
        
        # Update last login timestamp
        user.last_login_at = datetime.now(timezone.utc)
        self.db.commit()
        
        logger.info(f"User authenticated: {user.username}")
        return user
    
    def update_password(self, user_id: str, new_password: str) -> bool:
        """
        Update user password with validation.
        
        Returns:
            True if updated successfully, False otherwise
        """
        # Validate new password
        password_result = password_validator.validate(new_password)
        if not password_result.is_valid:
            raise ValidationError(password_result.errors)
        
        user = self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        
        user.hashed_password = get_password_hash(new_password)
        user.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        
        logger.info(f"Password updated for user: {user.username}")
        return True
    
    def check_username_available(self, username: str) -> tuple[bool, Optional[str]]:
        """
        Check if username is available.
        
        Returns:
            Tuple of (is_available, error_message)
        """
        # Validate format first
        result = username_validator.validate(username)
        if not result.is_valid:
            return False, result.errors[0]
        
        # Check database
        existing = self.get_by_username(username)
        if existing:
            return False, "Username is already taken"
        
        return True, None
    
    def check_email_available(self, email: str) -> tuple[bool, Optional[str]]:
        """
        Check if email is available.
        
        Returns:
            Tuple of (is_available, error_message)
        """
        # Validate format first
        result = email_validator.validate(email)
        if not result.is_valid:
            return False, result.errors[0]
        
        # Check database
        existing = self.get_by_email(email)
        if existing:
            return False, "Email is already registered"
        
        return True, None
    
    def validate_password_strength(self, password: str) -> dict:
        """
        Validate password and return detailed feedback.
        
        Returns:
            Dictionary with is_valid, errors, warnings, score, strength_label
        """
        result = password_validator.validate(password)
        score, label = password_validator.get_strength(password)
        
        return {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "score": score,
            "strength": label
        }


def get_user_service(db_session: Session) -> UserService:
    """Factory function to create UserService with session."""
    return UserService(db_session)
