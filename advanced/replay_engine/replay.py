"""Time-travel replay engine using Iceberg snapshots."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class ReplayEngine:
    """Replay historical events from Iceberg snapshots back into Kafka.

    Queries Iceberg tables at historical snapshots (time-travel) and
    re-publishes events to the replay_events topic for reprocessing.
    """

    REPLAY_TOPIC = "replay_events"

    def __init__(self, spark_session, kafka_producer) -> None:
        """Initialize the replay engine.

        Args:
            spark_session: Active SparkSession configured for Iceberg.
            kafka_producer: An aiokafka AIOKafkaProducer (already started).
        """
        self._spark = spark_session
        self._producer = kafka_producer
        self._cancelled = False
        self._progress = {"total": 0, "sent": 0, "failed": 0, "status": "idle"}

    @property
    def progress(self) -> dict:
        """Return current replay progress."""
        return dict(self._progress)

    def cancel(self) -> None:
        """Request cancellation of the running replay."""
        self._cancelled = True
        self._progress["status"] = "cancelling"
        logger.info("replay_cancel_requested")

    async def replay(
        self,
        table: str,
        start_time: datetime,
        end_time: datetime,
        customer_ids: Optional[list[str]] = None,
        batch_size: int = 100,
    ) -> dict:
        """Replay transactions from Iceberg table within a time range.

        Uses Iceberg's time-travel capability to query historical data
        and republish it to the replay topic.

        Args:
            table: Fully qualified Iceberg table name (e.g., "fraud_db.transactions").
            start_time: Start of the replay window.
            end_time: End of the replay window.
            customer_ids: Optional list of customer IDs to filter on.
            batch_size: Number of records to send per batch.

        Returns:
            Summary dict with total/sent/failed counts.
        """
        self._cancelled = False
        self._progress = {"total": 0, "sent": 0, "failed": 0, "status": "querying"}

        logger.info("replay_started",
                     table=table,
                     start=start_time.isoformat(),
                     end=end_time.isoformat(),
                     customer_filter=len(customer_ids) if customer_ids else "all")

        # Query Iceberg with time filter
        query = f"""
            SELECT * FROM {table}
            WHERE timestamp >= '{start_time.isoformat()}'
              AND timestamp <= '{end_time.isoformat()}'
        """
        if customer_ids:
            ids_str = ",".join(f"'{cid}'" for cid in customer_ids)
            query += f" AND customer_id IN ({ids_str})"

        query += " ORDER BY timestamp ASC"

        df = self._spark.sql(query)
        records = df.collect()
        self._progress["total"] = len(records)
        self._progress["status"] = "replaying"

        logger.info("replay_query_complete", record_count=len(records))

        # Send in batches
        batch: list[dict] = []
        for row in records:
            if self._cancelled:
                self._progress["status"] = "cancelled"
                logger.info("replay_cancelled", sent=self._progress["sent"])
                break

            record = row.asDict()
            # Convert non-serializable types
            for key, val in record.items():
                if isinstance(val, datetime):
                    record[key] = val.isoformat()
                elif hasattr(val, "item"):  # numpy types
                    record[key] = val.item()

            record["_replay"] = True
            record["_replay_timestamp"] = datetime.utcnow().isoformat()
            batch.append(record)

            if len(batch) >= batch_size:
                sent, failed = await self._send_batch(batch)
                self._progress["sent"] += sent
                self._progress["failed"] += failed
                batch.clear()

        # Flush remaining
        if batch and not self._cancelled:
            sent, failed = await self._send_batch(batch)
            self._progress["sent"] += sent
            self._progress["failed"] += failed

        if not self._cancelled:
            self._progress["status"] = "completed"

        logger.info("replay_finished", **self._progress)
        return self._progress

    async def _send_batch(self, batch: list[dict]) -> tuple[int, int]:
        """Send a batch of records to the replay topic.

        Returns:
            Tuple of (success_count, failure_count).
        """
        sent = 0
        failed = 0
        for record in batch:
            try:
                key = record.get("customer_id", "unknown")
                await self._producer.send_and_wait(
                    self.REPLAY_TOPIC,
                    value=json.dumps(record).encode("utf-8"),
                    key=key.encode("utf-8"),
                )
                sent += 1
            except Exception as exc:
                failed += 1
                logger.warning("replay_send_failed", error=str(exc))
        return sent, failed
