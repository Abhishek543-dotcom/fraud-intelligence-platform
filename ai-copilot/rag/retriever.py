"""Similarity search with filtering, reranking, and contextual compression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from ai_copilot.config import config
from ai_copilot.rag.vector_store import FraudVectorStore, get_vector_store

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedDocument:
    """A single document retrieved from the vector store."""

    content: str
    metadata: dict[str, Any]
    score: float  # cosine similarity (lower distance = higher relevance)
    doc_id: str


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""

    documents: list[RetrievedDocument]
    query: str
    total_candidates: int


class FraudRetriever:
    """Retrieves relevant fraud investigation context from ChromaDB."""

    def __init__(
        self,
        vector_store: FraudVectorStore | None = None,
        similarity_threshold: float | None = None,
        top_k: int | None = None,
        use_mmr: bool = True,
    ) -> None:
        self._store = vector_store or get_vector_store()
        self._threshold = similarity_threshold or config.similarity_threshold
        self._top_k = top_k or config.top_k
        self._use_mmr = use_mmr

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Retrieve documents relevant to the query with optional metadata filters."""
        k = top_k or self._top_k
        # Fetch more candidates for reranking
        fetch_k = k * 3 if self._use_mmr else k

        results = await self._store.query(
            query_text=query,
            n_results=fetch_k,
            where=filters,
        )

        documents = self._parse_results(results)
        total_candidates = len(documents)

        # Filter by similarity threshold (ChromaDB returns cosine distance, not similarity)
        documents = [
            doc for doc in documents if doc.score <= (1.0 - self._threshold)
        ]

        # Apply MMR for diversity if enabled
        if self._use_mmr and len(documents) > k:
            documents = self._mmr_rerank(documents, k)
        else:
            documents = documents[:k]

        logger.info(
            "retrieval_complete",
            query_length=len(query),
            candidates=total_candidates,
            returned=len(documents),
            filters=filters,
        )

        return RetrievalResult(
            documents=documents,
            query=query,
            total_candidates=total_candidates,
        )

    async def retrieve_for_customer(
        self,
        query: str,
        customer_id: str,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Retrieve documents filtered to a specific customer."""
        return await self.retrieve(
            query=query,
            filters={"customer_id": customer_id},
            top_k=top_k,
        )

    async def retrieve_by_alert_type(
        self,
        query: str,
        alert_type: str,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Retrieve documents filtered by fraud/alert type."""
        return await self.retrieve(
            query=query,
            filters={"alert_type": alert_type},
            top_k=top_k,
        )

    def _parse_results(self, results: dict[str, Any]) -> list[RetrievedDocument]:
        """Parse ChromaDB query results into RetrievedDocument objects."""
        documents: list[RetrievedDocument] = []
        if not results or not results.get("ids"):
            return documents

        ids = results["ids"][0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, content, metadata, distance in zip(ids, docs, metas, distances):
            documents.append(
                RetrievedDocument(
                    content=content or "",
                    metadata=metadata or {},
                    score=distance,
                    doc_id=doc_id,
                )
            )

        # Sort by relevance (lower distance = more relevant)
        documents.sort(key=lambda d: d.score)
        return documents

    def _mmr_rerank(
        self,
        documents: list[RetrievedDocument],
        k: int,
        lambda_mult: float = 0.5,
    ) -> list[RetrievedDocument]:
        """Maximum Marginal Relevance reranking for diversity.

        Balances relevance and diversity using lambda_mult parameter.
        Higher lambda_mult = more relevance, lower = more diversity.
        """
        if len(documents) <= k:
            return documents

        selected: list[RetrievedDocument] = [documents[0]]
        remaining = documents[1:]

        while len(selected) < k and remaining:
            best_score = float("inf")
            best_idx = 0

            for i, candidate in enumerate(remaining):
                # Relevance score (lower distance = better)
                relevance = candidate.score

                # Diversity: max similarity to any already-selected doc
                # We approximate by comparing content length overlap
                max_similarity = max(
                    _text_overlap(candidate.content, s.content) for s in selected
                )

                # MMR score: balance relevance and diversity
                mmr = lambda_mult * relevance + (1 - lambda_mult) * max_similarity
                if mmr < best_score:
                    best_score = mmr
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    def format_context(self, result: RetrievalResult) -> str:
        """Format retrieved documents into a context string for the LLM."""
        if not result.documents:
            return "No relevant context found for this query."

        parts: list[str] = []
        for i, doc in enumerate(result.documents, 1):
            meta_str = ", ".join(f"{k}: {v}" for k, v in doc.metadata.items() if v)
            parts.append(
                f"--- Document {i} [{meta_str}] ---\n{doc.content}"
            )

        return "\n\n".join(parts)


def _text_overlap(a: str, b: str) -> float:
    """Rough Jaccard overlap between two texts (word-level)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def get_retriever() -> FraudRetriever:
    """Return a module-level retriever instance."""
    return FraudRetriever()
