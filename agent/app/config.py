"""Agent service configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    
    # ChromaDB
    chroma_persist_directory: str = "/data/chroma"
    chroma_collection_name: str = "planning_documents"
    
    # PDF Data
    pdf_data_directory: str = "/data/pdfs"
    
    # Retrieval
    retrieval_top_k: int = 5
    # Optional: drop chunks with distance > this (Chroma L2; lower = better). None = no filter.
    retrieval_max_distance: float | None = None
    
    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
