"""Configuration for the AI Fraud Investigation Copilot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CopilotConfig:
    """Central configuration for all AI copilot components."""

    # --- Ollama LLM ---
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_HOST", "http://ollama:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "phi3:mini")
    )
    ollama_embedding_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )
    temperature: float = 0.1
    request_timeout: float = 30.0
    max_tokens: int = 2048

    # --- ChromaDB ---
    chromadb_host: str = field(
        default_factory=lambda: os.getenv("CHROMADB_HOST", "chromadb")
    )
    chromadb_port: int = field(
        default_factory=lambda: int(os.getenv("CHROMADB_PORT", "8000"))
    )
    collection_name: str = "fraud_investigations"
    embedding_dimension: int = 768

    # --- RAG Settings ---
    max_context_docs: int = 5
    top_k: int = 5
    similarity_threshold: float = 0.7
    chunk_size: int = 512
    chunk_overlap: int = 50

    # --- Conversation Memory ---
    memory_window_size: int = 5

    # --- Redis (for caching) ---
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0")
    )

    @property
    def chromadb_url(self) -> str:
        return f"http://{self.chromadb_host}:{self.chromadb_port}"


# Module-level singleton
config = CopilotConfig()
