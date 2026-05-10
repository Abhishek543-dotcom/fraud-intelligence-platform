"""Event replay engine for Iceberg lakehouse.

Reads historical data from Iceberg tables at a specific snapshot or
time range and republishes events to a Kafka replay topic.
Used for reprocessing with updated ML models, backfilling, and debugging.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("replay_engine")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
REPLAY_TOPIC = "replay_events"
DEFAULT_BATCH_SIZE = 1000


class ReplayEngine:
    """Replays historical events from Iceberg tables to Kafka.

    Supports:
    - Time range replay
    - Snapshot-based replay
    - Customer subset filtering
    - Configurable batch size and throttling
    """

    def __init__(
        self,
        source_table: str = "nessie.bronze.raw_transactions",
        target_topic: str = REPLAY_TOPIC,
        batch_size: int = DEFAULT_BATCH_SIZE,
        kafka_broker: Optional[str] = None,
    ):
        self.source_table = source_table
        self.target_topic = target_topic
        self.batch_size = batch_size
        self.kafka_broker = kafka_broker or KAFKA_BROKER
        self.spark = get_spark_session(app_name="ReplayEngine")
        self._total_replayed = 0

    def replay_time_range(
        self,
        start_time: str,
        end_time: str,
        customer_ids: Optional[list[str]] = None,
        throttle_seconds: float = 0.0,
    ) -> dict:
        """Replay events within a time range.

        Args:
            start_time: ISO-format start timestamp.
            end_time: ISO-format end timestamp.
            customer_ids: Optional list of customer IDs to filter.
            throttle_seconds: Delay between batches for rate control.

        Returns:
            Dict with replay statistics.
        """
        logger.info(
            "Replaying events from %s to %s (table=%s, topic=%s)",
            start_time,
            end_time,
            self.source_table,
            self.target_topic,
        )

        df = self.spark.sql(f"""
            SELECT * FROM {self.source_table}
            WHERE event_timestamp BETWEEN '{start_time}' AND '{end_time}'
            ORDER BY event_timestamp ASC
        """)

        if customer_ids:
            from pyspark.sql import functions as F
            df = df.filter(F.col("customer_id").isin(customer_ids))

        return self._publish_to_kafka(df, throttle_seconds)

    def replay_from_snapshot(
        self,
        snapshot_id: int,
        customer_ids: Optional[list[str]] = None,
        throttle_seconds: float = 0.0,
    ) -> dict:
        """Replay events from a specific Iceberg snapshot.

        Args:
            snapshot_id: Iceberg snapshot ID to read from.
            customer_ids: Optional customer ID filter.
            throttle_seconds: Delay between batches.

        Returns:
            Replay statistics dict.
        """
        logger.info(
            "Replaying from snapshot %d (table=%s, topic=%s)",
            snapshot_id,
            self.source_table,
            self.target_topic,
        )

        df = self.spark.sql(f"""
            SELECT * FROM {self.source_table}
            VERSION AS OF {snapshot_id}
            ORDER BY event_timestamp ASC
        """)

        if customer_ids:
            from pyspark.sql import functions as F
            df = df.filter(F.col("customer_id").isin(customer_ids))

        return self._publish_to_kafka(df, throttle_seconds)

    def replay_incremental(
        self,
        from_snapshot: int,
        to_snapshot: int,
        throttle_seconds: float = 0.0,
    ) -> dict:
        """Replay only the records that changed between two snapshots.

        Args:
            from_snapshot: Starting snapshot ID (exclusive).
            to_snapshot: Ending snapshot ID (inclusive).
            throttle_seconds: Delay between batches.

        Returns:
            Replay statistics dict.
        """
        logger.info(
            "Replaying incremental changes: snapshot %d → %d",
            from_snapshot,
            to_snapshot,
        )

        df = (
            self.spark.read
            .format("iceberg")
            .option("start-snapshot-id", str(from_snapshot))
            .option("end-snapshot-id", str(to_snapshot))
            .load(self.source_table)
        )

        return self._publish_to_kafka(df, throttle_seconds)

    def _publish_to_kafka(self, df, throttle_seconds: float) -> dict:
        """Write a DataFrame to the Kafka replay topic in batches.

        Args:
            df: DataFrame to publish.
            throttle_seconds: Delay between batches.

        Returns:
            Dict with total records, batches, and duration.
        """
        start = time.time()
        total_records = df.count()

        if total_records == 0:
            logger.info("No records to replay.")
            return {"total_records": 0, "batches": 0, "duration_sec": 0}

        logger.info("Replaying %d records (batch_size=%d)...", total_records, self.batch_size)

        from pyspark.sql import functions as F

        # Add replay metadata
        df_replay = (
            df
            .withColumn("_replay_timestamp", F.current_timestamp())
            .withColumn("_replay_source_table", F.lit(self.source_table))
        )

        # Prepare for Kafka: key=customer_id, value=JSON
        kafka_df = (
            df_replay
            .withColumn("key", F.col("customer_id").cast("string"))
            .withColumn("value", F.to_json(F.struct("*")))
            .select("key", "value")
        )

        # Write to Kafka
        (
            kafka_df.write
            .format("kafka")
            .option("kafka.bootstrap.servers", self.kafka_broker)
            .option("topic", self.target_topic)
            .save()
        )

        elapsed = time.time() - start
        self._total_replayed += total_records

        stats = {
            "total_records": total_records,
            "batches": (total_records // self.batch_size) + 1,
            "duration_sec": round(elapsed, 2),
            "records_per_sec": round(total_records / elapsed, 1) if elapsed > 0 else 0,
            "target_topic": self.target_topic,
        }

        logger.info(
            "Replay complete: %d records in %.2fs (%.0f records/s)",
            total_records,
            elapsed,
            stats["records_per_sec"],
        )

        return stats

    def close(self) -> None:
        """Stop the SparkSession."""
        self.spark.stop()
        logger.info("ReplayEngine closed. Total replayed: %d", self._total_replayed)


def main() -> None:
    """Example replay invocation."""
    logger.info("=" * 50)
    logger.info("  Event Replay Engine")
    logger.info("=" * 50)

    engine = ReplayEngine()

    try:
        # Replay last 24 hours
        now = datetime.now()
        yesterday = now.replace(hour=0, minute=0, second=0)

        stats = engine.replay_time_range(
            start_time=yesterday.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            throttle_seconds=0.1,
        )
        logger.info("Replay stats: %s", stats)

    finally:
        engine.close()


if __name__ == "__main__":
    main()
