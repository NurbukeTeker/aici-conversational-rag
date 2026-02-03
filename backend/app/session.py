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


# Global instance
session_service: SessionService | None = None


def get_session_service() -> SessionService:
    """Get session service instance (FastAPI dependency)."""
    global session_service
    if session_service is None:
        session_service = SessionService()
    return session_service
