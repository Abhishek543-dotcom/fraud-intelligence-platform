"""Index fraud cases, alerts, and documents into ChromaDB."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import structlog

from ai_copilot.config import config
from ai_copilot.rag.vector_store import FraudVectorStore, get_vector_store

logger = structlog.get_logger(__name__)


class FraudIndexer:
    """Indexes fraud alerts, investigation notes, and transaction context."""

    def __init__(
        self,
        vector_store: FraudVectorStore | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._store = vector_store or get_vector_store()
        self._chunk_size = chunk_size or config.chunk_size
        self._chunk_overlap = chunk_overlap or config.chunk_overlap

    async def index_fraud_alert(self, alert: dict[str, Any]) -> str:
        """Index a single fraud alert into ChromaDB.

        Expected alert keys: transaction_id, customer_id, amount, fraud_score,
        fraud_type, timestamp, merchant_id, location, features.
        """
        doc_id = f"alert_{alert.get('transaction_id', 'unknown')}"

        # Build document text from alert data
        text = self._format_alert_text(alert)
        chunks = self._split_text(text)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "doc_type": "fraud_alert",
                "transaction_id": str(alert.get("transaction_id", "")),
                "customer_id": str(alert.get("customer_id", "")),
                "fraud_type": str(alert.get("fraud_type", "")),
                "fraud_score": float(alert.get("fraud_score", 0.0)),
                "amount": float(alert.get("amount", 0.0)),
                "timestamp": str(alert.get("timestamp", "")),
                "indexed_at": datetime.utcnow().isoformat(),
            })

        await self._store.add_documents(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("alert_indexed", doc_id=doc_id, chunks=len(chunks))
        return doc_id

    async def index_investigation_note(
        self,
        case_id: str,
        note: str,
        analyst: str,
        customer_id: str | None = None,
    ) -> str:
        """Index an investigation note or analyst comment."""
        doc_id = f"note_{case_id}_{hashlib.md5(note.encode()).hexdigest()[:8]}"
        chunks = self._split_text(note)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            meta: dict[str, Any] = {
                "doc_type": "investigation_note",
                "case_id": case_id,
                "analyst": analyst,
                "indexed_at": datetime.utcnow().isoformat(),
            }
            if customer_id:
                meta["customer_id"] = customer_id
            metadatas.append(meta)

        await self._store.add_documents(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("note_indexed", doc_id=doc_id, chunks=len(chunks))
        return doc_id

    async def index_customer_context(
        self,
        customer_id: str,
        transaction_history: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
    ) -> str:
        """Index customer transaction history and profile for context retrieval."""
        doc_id = f"customer_{customer_id}"
        text = self._format_customer_text(customer_id, transaction_history, profile)
        chunks = self._split_text(text)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "doc_type": "customer_context",
                "customer_id": customer_id,
                "indexed_at": datetime.utcnow().isoformat(),
            })

        await self._store.add_documents(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("customer_context_indexed", doc_id=doc_id, chunks=len(chunks))
        return doc_id

    async def index_batch_alerts(self, alerts: list[dict[str, Any]]) -> int:
        """Index a batch of fraud alerts. Returns count of indexed alerts."""
        indexed = 0
        for alert in alerts:
            try:
                await self.index_fraud_alert(alert)
                indexed += 1
            except Exception as exc:
                logger.error(
                    "alert_indexing_failed",
                    transaction_id=alert.get("transaction_id"),
                    error=str(exc),
                )
        logger.info("batch_indexing_complete", total=len(alerts), indexed=indexed)
        return indexed

    def _format_alert_text(self, alert: dict[str, Any]) -> str:
        """Format a fraud alert into a readable text document."""
        lines = [
            f"Fraud Alert — Transaction {alert.get('transaction_id', 'N/A')}",
            f"Customer: {alert.get('customer_id', 'N/A')}",
            f"Amount: ${alert.get('amount', 0.0):.2f}",
            f"Merchant: {alert.get('merchant_id', 'N/A')}",
            f"Location: {alert.get('location', 'N/A')}",
            f"Timestamp: {alert.get('timestamp', 'N/A')}",
            f"Fraud Score: {alert.get('fraud_score', 0.0):.4f}",
            f"Fraud Type: {alert.get('fraud_type', 'unknown')}",
        ]

        features = alert.get("features", {})
        if features:
            lines.append("\nFeature Analysis:")
            for key, value in features.items():
                lines.append(f"  - {key}: {value}")

        explanation = alert.get("explanation", "")
        if explanation:
            lines.append(f"\nDetection Reason: {explanation}")

        return "\n".join(lines)

    def _format_customer_text(
        self,
        customer_id: str,
        transactions: list[dict[str, Any]],
        profile: dict[str, Any] | None,
    ) -> str:
        """Format customer data into a readable context document."""
        lines = [f"Customer Profile — {customer_id}"]

        if profile:
            for key, value in profile.items():
                lines.append(f"  {key}: {value}")

        lines.append(f"\nTransaction History ({len(transactions)} recent transactions):")
        for txn in transactions[-20:]:  # Limit to last 20
            lines.append(
                f"  [{txn.get('timestamp', 'N/A')}] "
                f"${txn.get('amount', 0.0):.2f} at {txn.get('merchant_id', 'N/A')} "
                f"({txn.get('location', 'N/A')})"
            )

        return "\n".join(lines)

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks using recursive character splitting."""
        if len(text) <= self._chunk_size:
            return [text]

        chunks: list[str] = []
        separators = ["\n\n", "\n", ". ", " "]

        self._recursive_split(text, separators, chunks)
        return chunks

    def _recursive_split(
        self,
        text: str,
        separators: list[str],
        chunks: list[str],
    ) -> None:
        """Recursively split text by separators to produce appropriately sized chunks."""
        if len(text) <= self._chunk_size:
            if text.strip():
                chunks.append(text.strip())
            return

        separator = separators[0] if separators else " "
        remaining_separators = separators[1:] if len(separators) > 1 else separators

        parts = text.split(separator)
        current_chunk = ""

        for part in parts:
            candidate = f"{current_chunk}{separator}{part}" if current_chunk else part

            if len(candidate) <= self._chunk_size:
                current_chunk = candidate
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                if len(part) > self._chunk_size:
                    # Part itself is too large, split recursively
                    self._recursive_split(part, remaining_separators, chunks)
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk.strip():
            chunks.append(current_chunk.strip())


def get_indexer() -> FraudIndexer:
    """Return a module-level indexer instance."""
    return FraudIndexer()
