"""Spark UDF for inline fraud scoring within streaming micro-batches."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

FEATURE_COLUMNS = [
    "tx_count_1h", "tx_count_24h", "amount", "amount_avg_7d",
    "amount_zscore", "geo_velocity_kmh", "merchant_risk_score",
    "device_consistency", "time_since_last_tx", "is_unusual_hour",
    "rapid_tx_count", "is_international", "card_present", "amount_to_avg_ratio",
]


def create_scoring_udf(model_server_url: str = "http://ml-service:8889"):
    """Create a Spark UDF that scores transactions via the model server.

    Returns a PySpark UDF that takes feature columns and returns a struct
    with fraud_probability and risk_level.
    """
    from pyspark.sql.functions import udf, struct, col
    from pyspark.sql.types import (
        StructType,
        StructField,
        FloatType,
        StringType,
    )

    result_schema = StructType([
        StructField("fraud_probability", FloatType(), False),
        StructField("risk_level", StringType(), False),
    ])

    @udf(returnType=result_schema)
    def score_transaction(
        tx_count_1h, tx_count_24h, amount, amount_avg_7d,
        amount_zscore, geo_velocity_kmh, merchant_risk_score,
        device_consistency, time_since_last_tx, is_unusual_hour,
        rapid_tx_count, is_international, card_present, amount_to_avg_ratio,
    ):
        """Score a single transaction via HTTP call to model server."""
        import requests

        features = {
            "tx_count_1h": float(tx_count_1h or 0),
            "tx_count_24h": float(tx_count_24h or 0),
            "amount": float(amount or 0),
            "amount_avg_7d": float(amount_avg_7d or 0),
            "amount_zscore": float(amount_zscore or 0),
            "geo_velocity_kmh": float(geo_velocity_kmh or 0),
            "merchant_risk_score": float(merchant_risk_score or 0),
            "device_consistency": float(device_consistency or 0),
            "time_since_last_tx": float(time_since_last_tx or 0),
            "is_unusual_hour": float(is_unusual_hour or 0),
            "rapid_tx_count": float(rapid_tx_count or 0),
            "is_international": float(is_international or 0),
            "card_present": float(card_present or 0),
            "amount_to_avg_ratio": float(amount_to_avg_ratio or 0),
        }

        try:
            resp = requests.post(
                f"{model_server_url}/predict",
                json=features,
                timeout=0.05,
            )
            if resp.status_code == 200:
                result = resp.json()
                return (result["fraud_probability"], result["risk_level"])
        except Exception:
            pass

        # Fallback: rule-based scoring
        score = _rule_based_fallback(features)
        level = "HIGH" if score >= 0.85 else "MEDIUM" if score >= 0.6 else "LOW" if score >= 0.4 else "NONE"
        return (score, level)

    return score_transaction


def _rule_based_fallback(features: dict[str, float]) -> float:
    """Rule-based fallback scoring when model server is unavailable."""
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


def create_batch_scoring_udf(model_server_url: str = "http://ml-service:8889"):
    """Create a Spark UDF that batches predictions within a partition.

    More efficient than per-row HTTP calls for micro-batch processing.
    Uses mapInPandas for partition-level batching.
    """
    import pandas as pd
    from pyspark.sql.types import (
        StructType,
        StructField,
        FloatType,
        StringType,
    )

    def score_partition(iterator):
        """Score an entire partition of transactions."""
        import requests

        for pdf in iterator:
            results = []
            batch_features = pdf[FEATURE_COLUMNS].to_dict("records")

            try:
                resp = requests.post(
                    f"{model_server_url}/predict/batch",
                    json={"transactions": batch_features},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    preds = resp.json()["predictions"]
                    for pred in preds:
                        results.append({
                            "fraud_probability": pred["fraud_probability"],
                            "risk_level": pred["risk_level"],
                        })
                else:
                    raise ValueError(f"Model server returned {resp.status_code}")
            except Exception:
                # Fallback for entire batch
                for row in batch_features:
                    score = _rule_based_fallback(row)
                    level = "HIGH" if score >= 0.85 else "MEDIUM" if score >= 0.6 else "LOW" if score >= 0.4 else "NONE"
                    results.append({
                        "fraud_probability": score,
                        "risk_level": level,
                    })

            result_df = pdf.copy()
            scores_df = pd.DataFrame(results)
            result_df["fraud_probability"] = scores_df["fraud_probability"]
            result_df["risk_level"] = scores_df["risk_level"]
            yield result_df

    return score_partition


def apply_scoring_to_stream(spark_df, model_server_url: str = "http://ml-service:8889"):
    """Apply fraud scoring to a streaming DataFrame.

    Uses the single-row UDF approach for simplicity.
    For higher throughput, use create_batch_scoring_udf with mapInPandas.
    """
    from pyspark.sql.functions import col

    score_udf = create_scoring_udf(model_server_url)

    scored = spark_df.withColumn(
        "fraud_score",
        score_udf(
            col("tx_count_1h"), col("tx_count_24h"), col("amount"),
            col("amount_avg_7d"), col("amount_zscore"), col("geo_velocity_kmh"),
            col("merchant_risk_score"), col("device_consistency"),
            col("time_since_last_tx"), col("is_unusual_hour"),
            col("rapid_tx_count"), col("is_international"),
            col("card_present"), col("amount_to_avg_ratio"),
        ),
    )

    return scored.withColumn(
        "fraud_probability", col("fraud_score.fraud_probability")
    ).withColumn(
        "risk_level", col("fraud_score.risk_level")
    ).drop("fraud_score")
