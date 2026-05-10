"""Dead Letter Queue handler for failed Kafka messages."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class DLQHandler:
    """Routes failed messages to the dead letter queue topic.

    Adds error metadata (reason, original topic, timestamp, retry count)
    to each DLQ message so that operators can diagnose and replay.
    """

    DLQ_TOPIC = "dlq_transactions"

    def __init__(self, producer) -> None:
        self._producer = producer
        self.dlq_count = 0

    async def send(self, original_message: dict, error_reason: str, source_topic: str) -> None:
        """Send a failed message to the DLQ with error metadata.

        Args:
            original_message: The original transaction dict that failed.
            error_reason: Human-readable error description.
            source_topic: The topic the message was originally destined for.
        """
        dlq_envelope = {
            "original_message": original_message,
            "error": {
                "reason": error_reason,
                "source_topic": source_topic,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "dlq_timestamp": time.time(),
            },
        }

        try:
            customer_id = original_message.get("customer_id", "unknown")
            await self._producer.send_and_wait(
                self.DLQ_TOPIC,
                value=json.dumps(dlq_envelope).encode("utf-8"),
                key=customer_id.encode("utf-8"),
            )
            self.dlq_count += 1
            logger.warning("message_sent_to_dlq",
                           customer_id=customer_id,
                           source_topic=source_topic,
                           reason=error_reason)
        except Exception as exc:
            # If DLQ itself fails, log and move on — we cannot infinitely recurse
            logger.error("dlq_send_failed",
                         error=str(exc),
                         customer_id=original_message.get("customer_id", "unknown"))
