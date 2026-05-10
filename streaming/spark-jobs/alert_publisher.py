"""Publish high-confidence fraud alerts to Kafka.

Filters transactions above the fraud score threshold, enriches them
with feature breakdown, and publishes structured alerts to the
fraud_alerts Kafka topic.
"""

import json
import logging
import os
import time
import uuid
from typing import Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
FRAUD_ALERTS_TOPIC = "fraud_alerts"
FRAUD_THRESHOLD_HIGH = 0.85
FRAUD_THRESHOLD_MEDIUM = 0.7


def classify_severity(fraud_score: float) -> str:
    """Classify alert severity based on fraud score."""
    if fraud_score >= FRAUD_THRESHOLD_HIGH:
        return "HIGH"
    elif fraud_score >= FRAUD_THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"


def recommended_action(severity: str) -> str:
    """Determine recommended action based on severity."""
    actions = {
        "HIGH": "BLOCK_TRANSACTION_AND_FREEZE_ACCOUNT",
        "MEDIUM": "FLAG_FOR_MANUAL_REVIEW",
        "LOW": "MONITOR_AND_LOG",
    }
    return actions.get(severity, "MONITOR_AND_LOG")


def publish_fraud_alerts(batch_df: DataFrame, batch_id: int) -> None:
    """Filter and publish fraud alerts from a micro-batch to Kafka.

    Transactions with fraud_score > 0.7 are published as structured alerts.

    Args:
        batch_df: Micro-batch DataFrame with fraud_score column.
        batch_id: Micro-batch identifier.
    """
    start = time.time()

    fraudulent = batch_df.filter(F.col("fraud_score") > FRAUD_THRESHOLD_MEDIUM)
    fraud_count = fraudulent.count()

    if fraud_count == 0:
        logger.debug("Alert batch %d: no fraud detected.", batch_id)
        return

    # Build alert payload
    alerts_df = (
        fraudulent
        .withColumn("alert_id", F.expr("uuid()"))
        .withColumn(
            "severity",
            F.when(F.col("fraud_score") >= FRAUD_THRESHOLD_HIGH, F.lit("HIGH"))
            .when(F.col("fraud_score") >= FRAUD_THRESHOLD_MEDIUM, F.lit("MEDIUM"))
            .otherwise(F.lit("LOW")),
        )
        .withColumn(
            "recommended_action",
            F.when(F.col("severity") == "HIGH", F.lit("BLOCK_TRANSACTION_AND_FREEZE_ACCOUNT"))
            .when(F.col("severity") == "MEDIUM", F.lit("FLAG_FOR_MANUAL_REVIEW"))
            .otherwise(F.lit("MONITOR_AND_LOG")),
        )
        .withColumn("alert_timestamp", F.current_timestamp())
        .withColumn("batch_id", F.lit(batch_id))
        # Build structured alert JSON
        .withColumn(
            "value",
            F.to_json(
                F.struct(
                    F.col("alert_id"),
                    F.col("transaction_id"),
                    F.col("customer_id"),
                    F.col("amount"),
                    F.col("currency"),
                    F.col("merchant_id"),
                    F.col("merchant_name"),
                    F.col("merchant_category"),
                    F.col("transaction_type"),
                    F.col("channel"),
                    F.col("latitude"),
                    F.col("longitude"),
                    F.col("city"),
                    F.col("country"),
                    F.col("event_timestamp"),
                    F.col("fraud_score"),
                    F.col("severity"),
                    F.col("recommended_action"),
                    F.col("alert_timestamp"),
                    # Feature breakdown for explainability
                    F.struct(
                        F.col("amount_zscore"),
                        F.col("geo_velocity_kmh"),
                        F.col("merchant_risk_score"),
                        F.col("device_consistency"),
                        F.col("time_since_last_tx"),
                        F.col("is_unusual_hour"),
                        F.col("rapid_tx_count"),
                        F.col("tx_count_1h"),
                    ).alias("feature_breakdown"),
                )
            ),
        )
        .withColumn("key", F.col("customer_id").cast("string"))
    )

    # Publish to Kafka
    (
        alerts_df
        .select("key", "value")
        .write
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("topic", FRAUD_ALERTS_TOPIC)
        .save()
    )

    elapsed = time.time() - start
    logger.info(
        "Alert batch %d: published %d fraud alerts in %.2fs",
        batch_id,
        fraud_count,
        elapsed,
    )
