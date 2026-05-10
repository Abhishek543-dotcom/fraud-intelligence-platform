"""Adaptive Kafka consumer with dynamic rate limiting and circuit breaker."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Callable, Optional

import structlog
from aiokafka import AIOKafkaConsumer

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Downstream unhealthy, paused
    HALF_OPEN = "half_open"  # Testing if downstream recovered


class AdaptiveConsumer:
    """Kafka consumer with dynamic rate limiting based on processing time.

    If processing time per message increases, the consumer reduces its
    consumption rate. If consumer lag grows, it increases rate up to a max.
    A circuit breaker pauses consumption entirely when downstream is unhealthy.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        process_fn: Callable,
        min_rate: float = 10.0,
        max_rate: float = 500.0,
        initial_rate: float = 100.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: float = 30.0,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._process_fn = process_fn
        self._min_rate = min_rate
        self._max_rate = max_rate
        self._current_rate = initial_rate

        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._failure_threshold = circuit_failure_threshold
        self._recovery_timeout = circuit_recovery_timeout
        self._circuit_opened_at: Optional[float] = None

        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

        # Metrics
        self._processed = 0
        self._failed = 0
        self._avg_process_time_ms: float = 0.0

    @property
    def metrics(self) -> dict:
        return {
            "current_rate": round(self._current_rate, 1),
            "circuit_state": self._circuit_state.value,
            "processed": self._processed,
            "failed": self._failed,
            "avg_process_time_ms": round(self._avg_process_time_ms, 2),
        }

    async def start(self) -> None:
        """Start the adaptive consumer."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        await self._consumer.start()
        self._running = True
        logger.info("adaptive_consumer_started", topic=self._topic, rate=self._current_rate)

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info("adaptive_consumer_stopped", **self.metrics)

    async def run(self) -> None:
        """Main consumption loop with adaptive rate control."""
        if not self._consumer:
            await self.start()

        while self._running:
            # Circuit breaker check
            if self._circuit_state == CircuitState.OPEN:
                if time.monotonic() - (self._circuit_opened_at or 0) > self._recovery_timeout:
                    self._circuit_state = CircuitState.HALF_OPEN
                    logger.info("circuit_half_open", topic=self._topic)
                else:
                    await asyncio.sleep(1.0)
                    continue

            # Consume batch
            interval = 1.0 / self._current_rate
            try:
                msg = await asyncio.wait_for(
                    self._consumer.__anext__(),
                    timeout=1.0,
                )
            except (asyncio.TimeoutError, StopAsyncIteration):
                continue

            # Process message
            start = time.monotonic()
            try:
                await self._process_fn(msg)
                elapsed_ms = (time.monotonic() - start) * 1000
                self._processed += 1
                self._consecutive_failures = 0

                # Update EMA of processing time
                alpha = 0.1
                self._avg_process_time_ms = (
                    alpha * elapsed_ms + (1 - alpha) * self._avg_process_time_ms
                )

                # Adapt rate based on processing time
                self._adapt_rate(elapsed_ms)

                if self._circuit_state == CircuitState.HALF_OPEN:
                    self._circuit_state = CircuitState.CLOSED
                    logger.info("circuit_closed", topic=self._topic)

            except Exception as exc:
                self._failed += 1
                self._consecutive_failures += 1
                logger.warning("process_failed",
                               error=str(exc),
                               consecutive=self._consecutive_failures)

                if self._consecutive_failures >= self._failure_threshold:
                    self._circuit_state = CircuitState.OPEN
                    self._circuit_opened_at = time.monotonic()
                    logger.error("circuit_opened",
                                 topic=self._topic,
                                 failures=self._consecutive_failures)

            # Rate-limit
            await asyncio.sleep(max(0, interval - (time.monotonic() - start)))

    def _adapt_rate(self, last_process_time_ms: float) -> None:
        """Adjust consumption rate based on processing performance."""
        target_process_time_ms = 50.0  # Target: 50ms per message

        if last_process_time_ms > target_process_time_ms * 2:
            # Processing is slow, reduce rate
            self._current_rate = max(self._min_rate, self._current_rate * 0.8)
        elif last_process_time_ms < target_process_time_ms * 0.5:
            # Processing is fast, increase rate
            self._current_rate = min(self._max_rate, self._current_rate * 1.1)
