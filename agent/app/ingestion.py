"""PDF ingestion and chunking service."""
import os
import logging
from pathlib import Path
from typing import Generator

from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from .config import get_settings

logger = logging.getLogger(__name__)


class PDFIngestionService:
    """Service for ingesting and chunking PDF documents."""
    
    def __init__(self):
        settings = get_settings()
        self.pdf_directory = Path(settings.pdf_data_directory)
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    def get_pdf_files(self) -> list[Path]:
        """Get all PDF files from the data directory."""
        if not self.pdf_directory.exists():
            logger.warning(f"PDF directory does not exist: {self.pdf_directory}")
            return []
        
        pdf_files = list(self.pdf_directory.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files")
        return pdf_files
    
    def extract_text_from_pdf(self, pdf_path: Path) -> list[dict]:
        """Extract text from PDF with page numbers."""
        pages = []
        try:
            reader = PdfReader(str(pdf_path))
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({
                        "page_num": page_num,
                        "text": text.strip(),
                        "source": pdf_path.name
                    })
            logger.info(f"Extracted {len(pages)} pages from {pdf_path.name}")
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
        
        return pages
    
    def detect_section(self, text: str) -> str | None:
        """Detect section title from text content."""
        # Look for common section patterns in planning documents
        section_patterns = [
            "Class A", "Class B", "Class C", "Class D", "Class E",
            "Class F", "Class G", "Class H",
            "General Issues", "Introduction", "Interpretation",
            "Conditions", "Development is not permitted"
        ]
        
        first_lines = text[:200].upper()
        for pattern in section_patterns:
            if pattern.upper() in first_lines:
                return pattern
        
        return None
    
    def chunk_pages(self, pages: list[dict]) -> Generator[dict, None, None]:
        """Chunk pages into smaller pieces with metadata."""
        chunk_counter = 0
        
        for page_data in pages:
            page_num = page_data["page_num"]
            source = page_data["source"]
            text = page_data["text"]
            
            # Split text into chunks
            chunks = self.text_splitter.split_text(text)
            
            for chunk_text in chunks:
                chunk_counter += 1
                section = self.detect_section(chunk_text)
                
                # Create unique chunk ID
                chunk_id = f"{source.replace('.pdf', '')}_{page_num:03d}_{chunk_counter:04d}"
                
                yield {
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "source": source,
                        "page": str(page_num),
                        "section": section,
                        "chunk_index": chunk_counter
                    }
                }
    
    def ingest_all(self) -> tuple[int, int]:
        """Ingest all PDFs and return (docs_processed, chunks_created)."""
        pdf_files = self.get_pdf_files()
        
        if not pdf_files:
            logger.warning("No PDF files found to ingest")
            return 0, 0
        
        all_chunks = []
        
        for pdf_path in pdf_files:
            pages = self.extract_text_from_pdf(pdf_path)
            chunks = list(self.chunk_pages(pages))
            all_chunks.extend(chunks)
            logger.info(f"Created {len(chunks)} chunks from {pdf_path.name}")
        
        return len(pdf_files), len(all_chunks)
    
    def get_chunks_for_storage(self) -> list[dict]:
        """Get all chunks ready for vector store."""
        pdf_files = self.get_pdf_files()
        all_chunks = []
        
        for pdf_path in pdf_files:
            pages = self.extract_text_from_pdf(pdf_path)
            chunks = list(self.chunk_pages(pages))
            all_chunks.extend(chunks)
        
        return all_chunks
