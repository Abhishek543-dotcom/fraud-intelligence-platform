"""Audit logger — writes API actions to the audit_logs Kafka topic."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Asynchronous audit logger that publishes events to Kafka.

    All API calls are logged with: timestamp, user_id, action, resource,
    IP address, and outcome. Logging is non-blocking to avoid impacting
    request latency.
    """

    TOPIC = "audit_logs"

    def __init__(self, kafka_producer) -> None:
        """Initialize with a Kafka producer instance.

        Args:
            kafka_producer: An aiokafka AIOKafkaProducer (already started).
        """
        self._producer = kafka_producer
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background flush loop."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("audit_logger_started")

    async def stop(self) -> None:
        """Stop the flush loop and drain remaining events."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Drain remaining
        while not self._queue.empty():
            event = self._queue.get_nowait()
            await self._send(event)
        logger.info("audit_logger_stopped")

    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        ip_address: str,
        outcome: str = "success",
        details: Optional[dict] = None,
    ) -> None:
        """Queue an audit event (non-blocking).

        Args:
            user_id: ID of the user performing the action.
            action: Action performed (e.g., "view_alert", "update_status").
            resource: Resource acted upon (e.g., "alerts/123").
            ip_address: Client IP address.
            outcome: "success" or "failure".
            details: Optional additional context.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "ip_address": ip_address,
            "outcome": outcome,
            "details": details or {},
        }
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("audit_queue_full", dropped_action=action)

    async def _flush_loop(self) -> None:
        """Background loop that flushes queued events to Kafka."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._send(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("audit_flush_error", error=str(exc))

    async def _send(self, event: dict) -> None:
        """Send a single audit event to Kafka."""
        try:
            key = event.get("user_id", "system")
            await self._producer.send_and_wait(
                self.TOPIC,
                value=json.dumps(event).encode("utf-8"),
                key=key.encode("utf-8"),
            )
        except Exception as exc:
            logger.error("audit_send_failed", error=str(exc), action=event.get("action"))
