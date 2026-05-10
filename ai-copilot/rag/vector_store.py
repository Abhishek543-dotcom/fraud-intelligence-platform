"""ChromaDB vector store operations for fraud investigation documents."""

from __future__ import annotations

from typing import Any

import chromadb
import structlog

from ai_copilot.config import config
from ai_copilot.rag.embeddings import get_embeddings_client

logger = structlog.get_logger(__name__)


class FraudVectorStore:
    """Manages ChromaDB collections for fraud investigation documents."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
    ) -> None:
        self._host = host or config.chromadb_host
        self._port = port or config.chromadb_port
        self._collection_name = collection_name or config.collection_name
        self._client: chromadb.HttpClient | None = None
        self._collection: chromadb.Collection | None = None

    @property
    def client(self) -> chromadb.HttpClient:
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=self._host,
                port=self._port,
            )
            logger.info(
                "chromadb_connected",
                host=self._host,
                port=self._port,
            )
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "chromadb_collection_ready",
                name=self._collection_name,
                count=self._collection.count(),
            )
        return self._collection

    async def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Add documents with embeddings and metadata to the collection."""
        embedder = get_embeddings_client()
        embeddings = await embedder.embed_batch(documents)

        self.collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("documents_added", count=len(documents))

    async def query(
        self,
        query_text: str,
        n_results: int | None = None,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query the collection by similarity with optional metadata filters."""
        n_results = n_results or config.top_k
        embedder = get_embeddings_client()
        query_embedding = await embedder.embed_text(query_text)

        query_params: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_params["where"] = where
        if where_document:
            query_params["where_document"] = where_document

        results = self.collection.query(**query_params)
        logger.debug(
            "vector_query_executed",
            n_results=n_results,
            returned=len(results.get("ids", [[]])[0]),
        )
        return results

    def delete_documents(self, ids: list[str]) -> None:
        """Delete documents by their IDs."""
        self.collection.delete(ids=ids)
        logger.info("documents_deleted", count=len(ids))

    def delete_collection(self) -> None:
        """Delete the entire collection."""
        self.client.delete_collection(self._collection_name)
        self._collection = None
        logger.info("collection_deleted", name=self._collection_name)

    def list_collections(self) -> list[str]:
        """List all collection names."""
        collections = self.client.list_collections()
        return [c.name for c in collections]

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self.collection.count()

    def health_check(self) -> bool:
        """Verify ChromaDB is reachable."""
        try:
            self.client.heartbeat()
            return True
        except Exception:
            return False


def get_vector_store() -> FraudVectorStore:
    """Return a module-level vector store instance."""
    return FraudVectorStore()
