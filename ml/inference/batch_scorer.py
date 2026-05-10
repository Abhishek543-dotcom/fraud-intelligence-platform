"""Batch scoring job for historical Iceberg data."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

FEATURE_COLUMNS = [
    "tx_count_1h", "tx_count_24h", "amount", "amount_avg_7d",
    "amount_zscore", "geo_velocity_kmh", "merchant_risk_score",
    "device_consistency", "time_since_last_tx", "is_unusual_hour",
    "rapid_tx_count", "is_international", "card_present", "amount_to_avg_ratio",
]


def create_spark_session(app_name: str = "FraudML-BatchScorer"):
    """Create Spark session with Iceberg configuration."""
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
        .config("spark.sql.catalog.nessie.uri", "http://nessie:19120/api/v1")
        .config("spark.sql.catalog.nessie.ref", "main")
        .config("spark.sql.catalog.nessie.warehouse", "s3://lakehouse/warehouse")
        .config("spark.sql.catalog.nessie.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin")
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin123")
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .getOrCreate()
    )


def score_batch(
    source_table: str = "nessie.fraud_db.silver_transactions",
    target_table: str = "nessie.fraud_db.gold_predictions",
    model_server_url: str = "http://ml-service:8889",
    batch_size: int = 1000,
    where_clause: str | None = None,
) -> dict[str, Any]:
    """Score an entire Iceberg table and write predictions to gold layer.

    Args:
        source_table: Iceberg source table with feature columns.
        target_table: Iceberg target table for predictions.
        model_server_url: URL of the model inference server.
        batch_size: Number of rows per prediction batch.
        where_clause: Optional SQL WHERE filter.

    Returns:
        Job summary with counts and timing.
    """
    import pandas as pd
    import requests
    from pyspark.sql import functions as F
    from pyspark.sql.types import FloatType, StringType, StructField, StructType

    spark = create_spark_session()
    start_time = time.time()

    logger.info(
        "batch_scoring_start",
        source=source_table,
        target=target_table,
        batch_size=batch_size,
    )

    # Read source
    query = f"SELECT * FROM {source_table}"
    if where_clause:
        query += f" WHERE {where_clause}"

    source_df = spark.sql(query)
    total_rows = source_df.count()
    logger.info("source_loaded", rows=total_rows)

    if total_rows == 0:
        logger.warning("no_rows_to_score")
        spark.stop()
        return {"status": "skipped", "rows_scored": 0}

    # Score using mapInPandas for efficiency
    def score_partition(iterator):
        for pdf in iterator:
            if pdf.empty:
                yield pdf
                continue

            batch_features = []
            for _, row in pdf.iterrows():
                features = {col: float(row.get(col, 0) or 0) for col in FEATURE_COLUMNS}
                batch_features.append(features)

            probabilities = []
            risk_levels = []

            # Process in sub-batches
            for i in range(0, len(batch_features), batch_size):
                chunk = batch_features[i : i + batch_size]
                try:
                    resp = requests.post(
                        f"{model_server_url}/predict/batch",
                        json={"transactions": chunk},
                        timeout=30.0,
                    )
                    if resp.status_code == 200:
                        preds = resp.json()["predictions"]
                        for p in preds:
                            probabilities.append(p["fraud_probability"])
                            risk_levels.append(p["risk_level"])
                    else:
                        for f in chunk:
                            probabilities.append(_fallback_score(f))
                            risk_levels.append(_fallback_level(probabilities[-1]))
                except Exception:
                    for f in chunk:
                        probabilities.append(_fallback_score(f))
                        risk_levels.append(_fallback_level(probabilities[-1]))

            pdf = pdf.copy()
            pdf["fraud_probability"] = probabilities
            pdf["risk_level"] = risk_levels
            pdf["scored_at"] = datetime.now(timezone.utc).isoformat()
            pdf["model_version"] = "batch"
            yield pdf

    # Define output schema (source schema + prediction columns)
    from pyspark.sql.types import StringType, FloatType

    output_schema = source_df.schema \
        .add("fraud_probability", FloatType()) \
        .add("risk_level", StringType()) \
        .add("scored_at", StringType()) \
        .add("model_version", StringType())

    scored_df = source_df.mapInPandas(score_partition, schema=output_schema)

    # Write to gold layer
    scored_df.writeTo(target_table).using("iceberg").createOrReplace()

    elapsed = time.time() - start_time
    rows_scored = scored_df.count()

    logger.info(
        "batch_scoring_complete",
        rows_scored=rows_scored,
        elapsed_seconds=round(elapsed, 2),
        throughput=round(rows_scored / elapsed, 1) if elapsed > 0 else 0,
    )

    spark.stop()

    return {
        "status": "completed",
        "source_table": source_table,
        "target_table": target_table,
        "rows_scored": rows_scored,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_rows_per_sec": round(rows_scored / elapsed, 1) if elapsed > 0 else 0,
    }


def _fallback_score(features: dict[str, float]) -> float:
    """Rule-based fallback scoring."""
    score = 0.0
    if features.get("amount_zscore", 0) > 3.0:
        score += 0.3
    if features.get("geo_velocity_kmh", 0) > 500:
        score += 0.25
    if features.get("device_consistency", 1) == 0:
        score += 0.15
    if features.get("rapid_tx_count", 0) > 5:
        score += 0.15
    if features.get("is_unusual_hour", 0) == 1:
        score += 0.1
    if features.get("merchant_risk_score", 0) > 0.7:
        score += 0.15
    return min(score, 1.0)


def _fallback_level(prob: float) -> str:
    if prob >= 0.85:
        return "HIGH"
    elif prob >= 0.60:
        return "MEDIUM"
    elif prob >= 0.40:
        return "LOW"
    return "NONE"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch fraud scoring job")
    parser.add_argument("--source", default="nessie.fraud_db.silver_transactions")
    parser.add_argument("--target", default="nessie.fraud_db.gold_predictions")
    parser.add_argument("--model-url", default="http://ml-service:8889")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--where", default=None)
    args = parser.parse_args()

    result = score_batch(
        source_table=args.source,
        target_table=args.target,
        model_server_url=args.model_url,
        batch_size=args.batch_size,
        where_clause=args.where,
    )
    print(json.dumps(result, indent=2))
