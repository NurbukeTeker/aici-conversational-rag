"""Redis session management service."""
import json
import logging
from datetime import datetime, timezone

import redis

from .config import get_settings

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing user sessions in Redis."""
    
    def __init__(self):
        settings = get_settings()
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True
        )
        self.ttl = settings.session_ttl_seconds
        logger.info(f"Redis session service initialized (host={settings.redis_host})")
    
    def _get_objects_key(self, user_id: str) -> str:
        """Get Redis key for user's session objects."""
        return f"session:{user_id}:objects"
    
    def _get_meta_key(self, user_id: str) -> str:
        """Get Redis key for session metadata."""
        return f"session:{user_id}:meta"
    
    def set_objects(self, user_id: str, objects: list[dict]) -> bool:
        """Store session objects for a user."""
        try:
            objects_key = self._get_objects_key(user_id)
            meta_key = self._get_meta_key(user_id)
            
            # Store objects as JSON
            self.redis_client.set(
                objects_key,
                json.dumps(objects),
                ex=self.ttl
            )
            
            # Store metadata
            meta = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "object_count": len(objects)
            }
            self.redis_client.set(
                meta_key,
                json.dumps(meta),
                ex=self.ttl
            )
            
            logger.info(f"Stored {len(objects)} objects for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing session objects: {e}")
            return False
    
    def get_objects(self, user_id: str) -> tuple[list[dict], dict | None]:
        """Get session objects and metadata for a user."""
        try:
            objects_key = self._get_objects_key(user_id)
            meta_key = self._get_meta_key(user_id)
            
            # Get objects
            objects_json = self.redis_client.get(objects_key)
            objects = json.loads(objects_json) if objects_json else []
            
            # Get metadata
            meta_json = self.redis_client.get(meta_key)
            meta = json.loads(meta_json) if meta_json else None
            
            return objects, meta
            
        except Exception as e:
            logger.error(f"Error getting session objects: {e}")
            return [], None
    
    def delete_session(self, user_id: str) -> bool:
        """Delete a user's session."""
        try:
            objects_key = self._get_objects_key(user_id)
            meta_key = self._get_meta_key(user_id)
            
            self.redis_client.delete(objects_key, meta_key)
            logger.info(f"Deleted session for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False


# Simple in-memory user store (for demo purposes)
# In production, use a proper database
class UserStore:
    """Simple in-memory user store."""
    
    def __init__(self):
        self._users: dict[str, dict] = {}
        self._email_index: dict[str, str] = {}
    
    def create_user(
        self,
        user_id: str,
        username: str,
        email: str,
        hashed_password: str
    ) -> dict:
        """Create a new user."""
        if username in self._users:
            raise ValueError(f"Username '{username}' already exists")
        if email in self._email_index:
            raise ValueError(f"Email '{email}' already registered")
        
        user = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "hashed_password": hashed_password
        }
        
        self._users[username] = user
        self._email_index[email] = username
        
        return user
    
    def get_user(self, username: str) -> dict | None:
        """Get user by username."""
        return self._users.get(username)
    
    def user_exists(self, username: str) -> bool:
        """Check if username exists."""
        return username in self._users


# Global instances
session_service: SessionService | None = None
user_store: UserStore | None = None


def get_session_service() -> SessionService:
    """Get session service instance."""
    global session_service
    if session_service is None:
        session_service = SessionService()
    return session_service


def get_user_store() -> UserStore:
    """Get user store instance."""
    global user_store
    if user_store is None:
        user_store = UserStore()
    return user_store
