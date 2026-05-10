"""Partition-aware, batched Kafka producer with idempotency."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import structlog
from aiokafka import AIOKafkaProducer

from .config import KAFKA_CONFIG
from .dlq_handler import DLQHandler

logger = structlog.get_logger(__name__)


class FraudKafkaProducer:
    """AsyncIO Kafka producer for the fraud intelligence pipeline.

    Features:
        - Partition-aware routing by customer_id for ordering guarantees
        - Snappy compression
        - Idempotent producer (exactly-once semantics)
        - Automatic DLQ routing for failed messages
        - Prometheus metrics
    """

    def __init__(self) -> None:
        self._producer: Optional[AIOKafkaProducer] = None
        self._dlq: Optional[DLQHandler] = None
        self._started = False

        # Metrics counters
        self.messages_sent = 0
        self.messages_failed = 0
        self.total_bytes_sent = 0
        self._last_latency_ms: float = 0.0

    async def start(self) -> None:
        """Start the Kafka producer and DLQ handler."""
        if self._started:
            return

        logger.info("starting_kafka_producer", bootstrap=KAFKA_CONFIG.bootstrap_servers)

        self._producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_CONFIG.bootstrap_servers,
            compression_type=KAFKA_CONFIG.compression_type,
            max_batch_size=KAFKA_CONFIG.batch_size,
            linger_ms=KAFKA_CONFIG.linger_ms,
            enable_idempotence=KAFKA_CONFIG.enable_idempotence,
            acks=KAFKA_CONFIG.acks,
            retry_backoff_ms=KAFKA_CONFIG.retry_backoff_ms,
            request_timeout_ms=KAFKA_CONFIG.request_timeout_ms,
            max_request_size=1048576,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )

        await self._producer.start()
        self._started = True

        self._dlq = DLQHandler(self._producer)
        logger.info("kafka_producer_started")

    async def stop(self) -> None:
        """Flush and stop the producer."""
        if self._producer and self._started:
            logger.info("stopping_kafka_producer",
                        total_sent=self.messages_sent,
                        total_failed=self.messages_failed)
            await self._producer.stop()
            self._started = False

    async def send_transaction(self, topic: str, transaction: dict) -> bool:
        """Send a single transaction to Kafka.

        Args:
            topic: Target Kafka topic.
            transaction: Serialized transaction dict.

        Returns:
            True if sent successfully, False if routed to DLQ.
        """
        if not self._started:
            raise RuntimeError("Producer not started. Call start() first.")

        customer_id = transaction.get("customer_id", "unknown")
        start_time = time.monotonic()

        for attempt in range(KAFKA_CONFIG.max_retries):
            try:
                result = await self._producer.send_and_wait(
                    topic,
                    value=transaction,
                    key=customer_id,
                )
                elapsed_ms = (time.monotonic() - start_time) * 1000
                self._last_latency_ms = elapsed_ms
                self.messages_sent += 1
                self.total_bytes_sent += len(json.dumps(transaction).encode("utf-8"))
                return True

            except Exception as exc:
                if attempt < KAFKA_CONFIG.max_retries - 1:
                    wait = KAFKA_CONFIG.retry_backoff_ms * (2 ** attempt) / 1000
                    logger.warning("send_retry",
                                   attempt=attempt + 1,
                                   max_retries=KAFKA_CONFIG.max_retries,
                                   error=str(exc),
                                   backoff_seconds=wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error("send_failed_to_dlq",
                                 topic=topic,
                                 customer_id=customer_id,
                                 error=str(exc))
                    self.messages_failed += 1
                    if self._dlq:
                        await self._dlq.send(transaction, str(exc), topic)
                    return False

        return False

    async def send_batch(self, topic: str, transactions: list[dict]) -> tuple[int, int]:
        """Send a batch of transactions.

        Returns:
            Tuple of (success_count, failure_count).
        """
        success = 0
        failure = 0
        for txn in transactions:
            ok = await self.send_transaction(topic, txn)
            if ok:
                success += 1
            else:
                failure += 1
        return success, failure

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    def get_metrics(self) -> dict:
        """Return current producer metrics."""
        return {
            "messages_sent": self.messages_sent,
            "messages_failed": self.messages_failed,
            "total_bytes_sent": self.total_bytes_sent,
            "last_latency_ms": round(self._last_latency_ms, 2),
        }
