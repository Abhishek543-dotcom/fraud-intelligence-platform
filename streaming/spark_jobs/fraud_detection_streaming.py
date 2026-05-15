"""Main Spark Structured Streaming pipeline for real-time fraud detection.

Pipeline: Kafka → Parse → Watermark → Features → Scoring → Fork (Bronze/Silver/Alerts)
"""

import logging
import os
import signal
import sys
import time
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import create_namespaces, get_spark_session
from streaming.spark_jobs.alert_publisher import publish_fraud_alerts
from streaming.spark_jobs.feature_engineering import add_all_features
from streaming.spark_jobs.iceberg_writer import (
    ensure_tables_exist,
    write_to_bronze,
    write_to_gold_fraud_metrics,
    write_to_silver,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("fraud_detection_streaming")

# Configuration
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
INPUT_TOPIC = "transactions_raw"
PROCESSING_TRIGGER = "10 seconds"
WATERMARK_DELAY = "30 seconds"
FRAUD_SCORE_THRESHOLD = 0.7

# Graceful shutdown flag
_shutdown_requested = False


def _signal_handler(signum: int, frame) -> None:
    global _shutdown_requested
    logger.info("Shutdown signal received (%s). Stopping gracefully...", signum)
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

# Transaction JSON schema matching the simulator output
TRANSACTION_SCHEMA = T.StructType([
    T.StructField("transaction_id", T.StringType(), False),
    T.StructField("customer_id", T.StringType(), False),
    T.StructField("amount", T.DoubleType(), False),
    T.StructField("currency", T.StringType(), True),
    T.StructField("merchant_id", T.StringType(), True),
    T.StructField("merchant_name", T.StringType(), True),
    T.StructField("merchant_category", T.StringType(), True),
    T.StructField("transaction_type", T.StringType(), True),
    T.StructField("channel", T.StringType(), True),
    T.StructField("device_id", T.StringType(), True),
    T.StructField("ip_address", T.StringType(), True),
    T.StructField("latitude", T.DoubleType(), True),
    T.StructField("longitude", T.DoubleType(), True),
    T.StructField("city", T.StringType(), True),
    T.StructField("country", T.StringType(), True),
    T.StructField("is_fraud", T.BooleanType(), True),
    T.StructField("event_timestamp", T.TimestampType(), False),
])


def compute_rule_based_fraud_score(df: DataFrame) -> DataFrame:
    """Compute a composite fraud score using rule-based heuristics on features.

    Weighted combination of features, each normalized to [0, 1].

    Score = w1*amount_zscore_norm + w2*geo_velocity_norm + w3*merchant_risk +
            w4*(1-device_consistency) + w5*unusual_hour + w6*rapid_tx_norm
    """
    df_scored = (
        df
        # Normalize amount_zscore: clip to [0, 5], then divide by 5
        .withColumn(
            "_az_norm",
            F.least(F.greatest(F.abs(F.col("amount_zscore")), F.lit(0.0)), F.lit(5.0)) / 5.0,
        )
        # Normalize geo_velocity: anything > 900 km/h is suspicious (impossible travel)
        .withColumn(
            "_gv_norm",
            F.least(F.col("geo_velocity_kmh") / 900.0, F.lit(1.0)),
        )
        # Rapid transaction count: > 5 in 5 min is highly suspicious
        .withColumn(
            "_rt_norm",
            F.least(F.col("rapid_tx_count").cast("double") / 5.0, F.lit(1.0)),
        )
        # Weighted fraud score
        .withColumn(
            "fraud_score",
            F.round(
                F.lit(0.25) * F.col("_az_norm")
                + F.lit(0.20) * F.col("_gv_norm")
                + F.lit(0.15) * F.col("merchant_risk_score")
                + F.lit(0.15) * (F.lit(1.0) - F.col("device_consistency"))
                + F.lit(0.10) * F.col("is_unusual_hour").cast("double")
                + F.lit(0.15) * F.col("_rt_norm"),
                4,
            ),
        )
        .drop("_az_norm", "_gv_norm", "_rt_norm")
    )

    return df_scored


def process_micro_batch(batch_df: DataFrame, batch_id: int) -> None:
    """Process a single micro-batch through the full pipeline.

    Writes to bronze, silver, gold, and publishes fraud alerts.

    Args:
        batch_df: Micro-batch DataFrame.
        batch_id: Batch identifier.
    """
    start = time.time()
    record_count = batch_df.count()

    if record_count == 0:
        logger.debug("Batch %d: empty.", batch_id)
        return

    logger.info("Batch %d: processing %d records...", batch_id, record_count)

    # Branch 1: Write raw data to bronze (append)
    try:
        write_to_bronze(batch_df, batch_id)
    except Exception as e:
        logger.error("Batch %d: bronze write failed: %s", batch_id, e)

    # Feature engineering
    df_featured = add_all_features(batch_df)

    # Fraud scoring
    df_scored = compute_rule_based_fraud_score(df_featured)

    # Branch 2: Write enriched data to silver (merge/upsert)
    try:
        write_to_silver(df_scored, batch_id)
    except Exception as e:
        logger.error("Batch %d: silver write failed: %s", batch_id, e)

    # Branch 3: Publish fraud alerts
    try:
        publish_fraud_alerts(df_scored, batch_id)
    except Exception as e:
        logger.error("Batch %d: alert publish failed: %s", batch_id, e)

    # Update gold fraud metrics
    try:
        write_to_gold_fraud_metrics(df_scored, batch_id)
    except Exception as e:
        logger.error("Batch %d: gold metrics write failed: %s", batch_id, e)

    elapsed = time.time() - start
    logger.info(
        "Batch %d: completed %d records in %.2fs (%.0f records/s)",
        batch_id,
        record_count,
        elapsed,
        record_count / elapsed if elapsed > 0 else 0,
    )


def build_streaming_pipeline(spark: SparkSession) -> None:
    """Build and start the main streaming pipeline.

    Reads from Kafka, parses JSON, applies watermark, and processes
    via foreachBatch sink.
    """
    logger.info("Starting fraud detection streaming pipeline...")
    logger.info("  Kafka broker: %s", KAFKA_BROKER)
    logger.info("  Input topic: %s", INPUT_TOPIC)
    logger.info("  Trigger: %s", PROCESSING_TRIGGER)
    logger.info("  Watermark delay: %s", WATERMARK_DELAY)

    # Read from Kafka
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", INPUT_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", 10000)
        .load()
    )

    # Parse JSON from Kafka value
    parsed_stream = (
        raw_stream
        .select(
            F.col("key").cast("string").alias("kafka_key"),
            F.from_json(F.col("value").cast("string"), TRANSACTION_SCHEMA).alias("data"),
            F.col("timestamp").alias("kafka_timestamp"),
            F.col("partition").alias("kafka_partition"),
            F.col("offset").alias("kafka_offset"),
        )
        .select("kafka_key", "kafka_timestamp", "kafka_partition", "kafka_offset", "data.*")
        .filter(F.col("transaction_id").isNotNull())
        # Apply watermark on event_timestamp for late data handling
        .withWatermark("event_timestamp", WATERMARK_DELAY)
    )

    # Start streaming query with foreachBatch
    query = (
        parsed_stream.writeStream
        .foreachBatch(process_micro_batch)
        .option(
            "checkpointLocation",
            "s3a://spark-checkpoints/fraud-detection-streaming/",
        )
        .trigger(processingTime=PROCESSING_TRIGGER)
        .queryName("fraud_detection_pipeline")
        .start()
    )

    logger.info("Streaming query started: %s", query.id)

    # Await termination with periodic status logging
    while not _shutdown_requested:
        if query.isActive:
            status = query.status
            logger.info(
                "Stream status: isDataAvailable=%s, isTriggerActive=%s, message='%s'",
                status.get("isDataAvailable"),
                status.get("isTriggerActive"),
                status.get("message", ""),
            )
            try:
                query.awaitTermination(timeout=30)
                if not query.isActive:
                    break
            except Exception:
                break
        else:
            logger.warning("Stream query is no longer active.")
            break

    logger.info("Stopping streaming query...")
    if query.isActive:
        query.stop()
    logger.info("Streaming query stopped.")


def main() -> None:
    """Entry point for the fraud detection streaming job."""
    logger.info("=" * 60)
    logger.info("  Fraud Detection Streaming Pipeline")
    logger.info("=" * 60)

    spark = get_spark_session(app_name="FraudDetectionStreaming")

    try:
        # Initialize catalog and tables
        create_namespaces(spark)
        ensure_tables_exist(spark)

        # Run the pipeline
        build_streaming_pipeline(spark)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.exception("Fatal error in streaming pipeline: %s", e)
        sys.exit(1)
    finally:
        spark.stop()
        logger.info("SparkSession stopped. Goodbye.")


if __name__ == "__main__":
    main()
