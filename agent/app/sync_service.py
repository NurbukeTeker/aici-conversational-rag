"""Document Sync Service - Idempotent incremental ingestion."""
import logging
from pathlib import Path
from dataclasses import dataclass

from .config import get_settings
from .document_registry import DocumentRegistry, DocumentStatus
from .ingestion import PDFIngestionService
from .vector_store import VectorStoreService

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    new_documents: int = 0
    updated_documents: int = 0
    unchanged_documents: int = 0
    deleted_documents: int = 0
    total_chunks_added: int = 0
    total_chunks_deleted: int = 0
    errors: list[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def has_changes(self) -> bool:
        return (self.new_documents + self.updated_documents + self.deleted_documents) > 0
    
    def to_dict(self) -> dict:
        return {
            "new_documents": self.new_documents,
            "updated_documents": self.updated_documents,
            "unchanged_documents": self.unchanged_documents,
            "deleted_documents": self.deleted_documents,
            "total_chunks_added": self.total_chunks_added,
            "total_chunks_deleted": self.total_chunks_deleted,
            "has_changes": self.has_changes,
            "errors": self.errors
        }


class DocumentSyncService:
    """
    Service for synchronizing PDF documents with the vector store.
    
    Implements idempotent incremental sync:
    - NEW: Document not in registry → ingest
    - UNCHANGED: Same content hash → skip
    - UPDATED: Different content hash → delete old chunks + re-ingest
    - DELETED: In registry but file missing → delete chunks
    """
    
    def __init__(
        self,
        registry: DocumentRegistry,
        ingestion_service: PDFIngestionService,
        vector_store: VectorStoreService
    ):
        self.registry = registry
        self.ingestion = ingestion_service
        self.vector_store = vector_store
        self.settings = get_settings()
    
    def sync(self, delete_missing: bool = False) -> SyncResult:
        """
        Perform incremental sync of all PDF documents.
        
        Args:
            delete_missing: If True, delete chunks for documents no longer in source
        
        Returns:
            SyncResult with statistics
        """
        result = SyncResult()
        
        # Get all PDF files from source directory
        pdf_files = self.ingestion.get_pdf_files()
        current_sources = {pdf.name for pdf in pdf_files}
        
        logger.info(f"Starting sync: {len(pdf_files)} PDF files found")
        
        # Process each PDF file
        for pdf_path in pdf_files:
            try:
                self._process_document(pdf_path, result)
            except Exception as e:
                error_msg = f"Error processing {pdf_path.name}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        
        # Handle deleted documents (optional)
        if delete_missing:
            deleted_sources = self.registry.get_deleted_sources(current_sources)
            for source_id in deleted_sources:
                try:
                    self._delete_document(source_id, result)
                except Exception as e:
                    error_msg = f"Error deleting {source_id}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
        
        logger.info(
            f"Sync complete: {result.new_documents} new, "
            f"{result.updated_documents} updated, "
            f"{result.unchanged_documents} unchanged, "
            f"{result.deleted_documents} deleted"
        )
        
        return result
    
    def _process_document(self, pdf_path: Path, result: SyncResult) -> None:
        """Process a single document."""
        source_id = pdf_path.name
        content_hash = self.registry.compute_hash(pdf_path)
        status = self.registry.get_status(source_id, content_hash)
        
        logger.debug(f"Document {source_id}: status={status.value}, hash={content_hash[:8]}...")
        
        if status == DocumentStatus.UNCHANGED:
            result.unchanged_documents += 1
            logger.debug(f"Skipping unchanged document: {source_id}")
            return
        
        if status == DocumentStatus.UPDATED:
            # Delete old chunks first
            old_chunk_ids = self.registry.get_chunk_ids(source_id)
            if old_chunk_ids:
                deleted = self.vector_store.delete_by_ids(old_chunk_ids)
                result.total_chunks_deleted += deleted
                logger.info(f"Deleted {deleted} old chunks for updated document: {source_id}")
        
        # Extract and chunk the document
        pages = self.ingestion.extract_text_from_pdf(pdf_path)
        chunks = list(self.ingestion.chunk_pages(pages))
        
        if not chunks:
            logger.warning(f"No chunks extracted from {source_id}")
            return
        
        # Add to vector store
        chunk_ids = [chunk["id"] for chunk in chunks]
        self.vector_store.add_documents(chunks)
        
        # Register in registry
        self.registry.register(
            source_id=source_id,
            content_hash=content_hash,
            chunk_ids=chunk_ids,
            page_count=len(pages)
        )
        
        result.total_chunks_added += len(chunks)
        
        if status == DocumentStatus.NEW:
            result.new_documents += 1
            logger.info(f"Ingested NEW document: {source_id} ({len(chunks)} chunks)")
        else:
            result.updated_documents += 1
            logger.info(f"Re-ingested UPDATED document: {source_id} ({len(chunks)} chunks)")
    
    def _delete_document(self, source_id: str, result: SyncResult) -> None:
        """Delete a document that no longer exists in source."""
        chunk_ids = self.registry.unregister(source_id)
        
        if chunk_ids:
            deleted = self.vector_store.delete_by_ids(chunk_ids)
            result.total_chunks_deleted += deleted
        
        result.deleted_documents += 1
        logger.info(f"Deleted document no longer in source: {source_id}")
    
    def force_reingest(self, source_id: str | None = None) -> SyncResult:
        """
        Force re-ingestion of specific document or all documents.
        
        Args:
            source_id: Specific document to re-ingest, or None for all
        """
        if source_id:
            # Clear specific document from registry to force re-ingest
            self.registry.unregister(source_id)
            # Find and process that specific file
            pdf_files = [
                f for f in self.ingestion.get_pdf_files() 
                if f.name == source_id
            ]
        else:
            # Clear entire registry and vector store
            self.registry.clear()
            self.vector_store.clear()
            pdf_files = self.ingestion.get_pdf_files()
        
        result = SyncResult()
        for pdf_path in pdf_files:
            try:
                self._process_document(pdf_path, result)
            except Exception as e:
                result.errors.append(f"Error processing {pdf_path.name}: {e}")
        
        return result
    
    def get_status(self) -> dict:
        """Get current sync status."""
        records = self.registry.get_all_records()
        return {
            "registered_documents": len(records),
            "total_chunks": sum(r.chunk_count for r in records.values()),
            "vector_store_count": self.vector_store.count(),
            "documents": [
                {
                    "source_id": r.source_id,
                    "version": r.version,
                    "chunk_count": r.chunk_count,
                    "page_count": r.page_count,
                    "last_ingested_at": r.last_ingested_at,
                    "content_hash": r.content_hash[:16] + "..."
                }
                for r in records.values()
            ]
        }
