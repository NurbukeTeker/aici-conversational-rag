"""Document Registry for idempotent PDF ingestion with content hashing."""
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class DocumentStatus(Enum):
    """Document sync status."""
    NEW = "new"
    UNCHANGED = "unchanged"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class DocumentRecord:
    """Registry record for a document."""
    source_id: str
    content_hash: str
    chunk_ids: list[str]
    version: int
    last_ingested_at: str
    page_count: int = 0
    chunk_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentRecord":
        return cls(**data)


class DocumentRegistry:
    """
    Registry for tracking document versions and enabling idempotent ingestion.
    
    Features:
    - Content hashing (SHA256) for change detection
    - Incremental sync (NEW, UNCHANGED, UPDATED, DELETED)
    - Chunk ID tracking for selective deletion
    - Persistent registry file
    """
    
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self.records: dict[str, DocumentRecord] = {}
        self._load()
    
    def _load(self) -> None:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                    self.records = {
                        k: DocumentRecord.from_dict(v) 
                        for k, v in data.items()
                    }
                logger.info(f"Loaded registry with {len(self.records)} documents")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}, starting fresh")
                self.records = {}
        else:
            logger.info("No existing registry, starting fresh")
    
    def _save(self) -> None:
        """Persist registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(
                {k: v.to_dict() for k, v in self.records.items()},
                f,
                indent=2
            )
        logger.debug(f"Registry saved with {len(self.records)} documents")
    
    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA256 hash of file contents."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def get_status(self, source_id: str, content_hash: str) -> DocumentStatus:
        """Determine document status based on registry."""
        if source_id not in self.records:
            return DocumentStatus.NEW
        
        existing = self.records[source_id]
        if existing.content_hash == content_hash:
            return DocumentStatus.UNCHANGED
        else:
            return DocumentStatus.UPDATED
    
    def get_deleted_sources(self, current_sources: set[str]) -> list[str]:
        """Find sources in registry but not in current file list."""
        registered = set(self.records.keys())
        return list(registered - current_sources)
    
    def register(
        self,
        source_id: str,
        content_hash: str,
        chunk_ids: list[str],
        page_count: int = 0
    ) -> None:
        """Register or update a document in the registry."""
        existing = self.records.get(source_id)
        version = (existing.version + 1) if existing else 1
        
        self.records[source_id] = DocumentRecord(
            source_id=source_id,
            content_hash=content_hash,
            chunk_ids=chunk_ids,
            version=version,
            last_ingested_at=datetime.now(timezone.utc).isoformat(),
            page_count=page_count,
            chunk_count=len(chunk_ids)
        )
        self._save()
        logger.info(f"Registered document: {source_id} (v{version}, {len(chunk_ids)} chunks)")
    
    def unregister(self, source_id: str) -> list[str]:
        """Remove document from registry, return its chunk IDs for deletion."""
        if source_id in self.records:
            chunk_ids = self.records[source_id].chunk_ids
            del self.records[source_id]
            self._save()
            logger.info(f"Unregistered document: {source_id}")
            return chunk_ids
        return []
    
    def get_chunk_ids(self, source_id: str) -> list[str]:
        """Get chunk IDs for a document."""
        if source_id in self.records:
            return self.records[source_id].chunk_ids
        return []
    
    def get_all_records(self) -> dict[str, DocumentRecord]:
        """Get all registry records."""
        return self.records.copy()
    
    def clear(self) -> None:
        """Clear the entire registry."""
        self.records = {}
        self._save()
        logger.info("Registry cleared")
