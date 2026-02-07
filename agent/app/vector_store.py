"""ChromaDB vector store service."""
import logging
from pathlib import Path

from .config import get_settings
from .chroma_client import get_chroma_client

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Service for managing ChromaDB vector store (uses shared Chroma client)."""
    
    def __init__(self):
        settings = get_settings()
        self.persist_directory = Path(settings.chroma_persist_directory)
        self.collection_name = settings.chroma_collection_name
        
        self.client = get_chroma_client()
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Planning/regulatory documents for RAG"}
        )
        
        logger.info(f"Vector store initialized at {self.persist_directory}")
        logger.info(f"Collection '{self.collection_name}' has {self.collection.count()} documents")
    
    def add_documents(self, chunks: list[dict]) -> int:
        """Add document chunks to the vector store."""
        if not chunks:
            logger.warning("No chunks provided to add")
            return 0
        
        ids = [chunk["id"] for chunk in chunks]
        documents = [chunk["text"] for chunk in chunks]
        # ChromaDB doesn't accept None values in metadata - filter them out
        metadatas = [
            {k: v for k, v in chunk["metadata"].items() if v is not None}
            for chunk in chunks
        ]
        
        # Add in batches to avoid memory issues
        batch_size = 100
        total_added = 0
        
        for i in range(0, len(chunks), batch_size):
            batch_ids = ids[i:i + batch_size]
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]
            
            self.collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta
            )
            total_added += len(batch_ids)
            logger.info(f"Added batch of {len(batch_ids)} documents")
        
        logger.info(f"Total documents added: {total_added}")
        return total_added
    
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for relevant documents."""
        if self.collection.count() == 0:
            logger.warning("Vector store is empty, cannot search")
            return []
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        formatted_results = []
        
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                formatted_results.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "source": metadata.get("source", "unknown"),
                    "page": metadata.get("page"),
                    "section": metadata.get("section"),
                    "distance": results["distances"][0][i] if results["distances"] else None
                })
        
        logger.info(f"Search returned {len(formatted_results)} results for query: {query[:50]}...")
        return formatted_results
    
    def count(self) -> int:
        """Get the number of documents in the collection."""
        return self.collection.count()
    
    def clear(self) -> None:
        """Clear all documents from the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"description": "Planning/regulatory documents for RAG"}
        )
        logger.info("Vector store cleared")
    
    def delete_by_ids(self, chunk_ids: list[str]) -> int:
        """Delete specific chunks by their IDs."""
        if not chunk_ids:
            return 0
        
        try:
            self.collection.delete(ids=chunk_ids)
            logger.info(f"Deleted {len(chunk_ids)} chunks from vector store")
            return len(chunk_ids)
        except Exception as e:
            logger.error(f"Error deleting chunks: {e}")
            return 0
    
    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a specific source document."""
        try:
            # Query to find all chunks with this source
            results = self.collection.get(
                where={"source": source},
                include=[]
            )
            
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} chunks for source: {source}")
                return len(results["ids"])
            return 0
        except Exception as e:
            logger.error(f"Error deleting chunks by source: {e}")
            return 0
    
    def is_ready(self) -> bool:
        """Check if vector store has documents."""
        return self.collection.count() > 0
