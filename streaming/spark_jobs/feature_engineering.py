"""Feature engineering for real-time fraud detection.

Computes 10 features per transaction using Spark Structured Streaming
windowed aggregations and stateful operations.
"""

import logging
import math
from typing import Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window

logger = logging.getLogger(__name__)

# Earth radius in km for Haversine calculation
EARTH_RADIUS_KM = 6371.0


@F.udf(T.DoubleType())
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """Calculate distance in km between two GPS coordinates using Haversine formula."""
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return None
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


@F.udf(T.BooleanType())
def is_unusual_hour_udf(hour: int) -> Optional[bool]:
    """Flag transactions between midnight and 5 AM as unusual."""
    if hour is None:
        return None
    return hour >= 0 and hour < 5


def compute_windowed_features(df: DataFrame) -> DataFrame:
    """Compute windowed aggregation features per customer.

    Features computed:
        - tx_count_1h: Transaction count in 1-hour window
        - tx_count_24h: Transaction count in 24-hour window
        - rapid_tx_count: Transaction count in 5-minute window (card testing)

    Args:
        df: Streaming DataFrame with watermark applied on event_timestamp.

    Returns:
        DataFrame with windowed count features joined back.
    """
    # 1-hour window counts
    counts_1h = (
        df.groupBy(
            F.col("customer_id"),
            F.window("event_timestamp", "1 hour", "5 minutes"),
        )
        .agg(F.count("*").alias("tx_count_1h"))
        .select(
            F.col("customer_id").alias("_cid_1h"),
            F.col("window.end").alias("_window_end_1h"),
            F.col("tx_count_1h"),
        )
    )

    # 5-minute rapid window (card testing detection)
    counts_5m = (
        df.groupBy(
            F.col("customer_id"),
            F.window("event_timestamp", "5 minutes", "1 minute"),
        )
        .agg(F.count("*").alias("rapid_tx_count"))
        .select(
            F.col("customer_id").alias("_cid_5m"),
            F.col("window.end").alias("_window_end_5m"),
            F.col("rapid_tx_count"),
        )
    )

    return counts_1h, counts_5m


def compute_per_transaction_features(df: DataFrame) -> DataFrame:
    """Compute features that apply to each individual transaction.

    Features computed:
        - amount_zscore: Z-score of current amount relative to customer's running stats
        - geo_velocity_kmh: Travel speed from last transaction location
        - time_since_last_tx: Seconds since previous transaction
        - is_unusual_hour: Boolean flag for late-night transactions
        - device_consistency: 1.0 if device matches historical, 0.0 if new

    Args:
        df: Streaming DataFrame with transaction fields.

    Returns:
        DataFrame with new feature columns appended.
    """
    customer_window = Window.partitionBy("customer_id").orderBy("event_timestamp")

    df_features = (
        df
        # Time-based features
        .withColumn("_prev_timestamp", F.lag("event_timestamp").over(customer_window))
        .withColumn(
            "time_since_last_tx",
            F.when(
                F.col("_prev_timestamp").isNotNull(),
                F.unix_timestamp("event_timestamp") - F.unix_timestamp("_prev_timestamp"),
            ).otherwise(F.lit(None).cast(T.LongType())),
        )
        # Geographic velocity
        .withColumn("_prev_latitude", F.lag("latitude").over(customer_window))
        .withColumn("_prev_longitude", F.lag("longitude").over(customer_window))
        .withColumn(
            "_distance_km",
            haversine_km(
                F.col("_prev_latitude"),
                F.col("_prev_longitude"),
                F.col("latitude"),
                F.col("longitude"),
            ),
        )
        .withColumn(
            "geo_velocity_kmh",
            F.when(
                (F.col("time_since_last_tx").isNotNull()) & (F.col("time_since_last_tx") > 0),
                F.col("_distance_km") / (F.col("time_since_last_tx") / 3600.0),
            ).otherwise(F.lit(0.0)),
        )
        # Unusual hour flag
        .withColumn("_hour", F.hour("event_timestamp"))
        .withColumn("is_unusual_hour", is_unusual_hour_udf(F.col("_hour")))
        # Device consistency: compare device_id to most recent known device
        .withColumn("_prev_device", F.lag("device_id").over(customer_window))
        .withColumn(
            "device_consistency",
            F.when(F.col("_prev_device").isNull(), F.lit(0.5))
            .when(F.col("device_id") == F.col("_prev_device"), F.lit(1.0))
            .otherwise(F.lit(0.0)),
        )
        # Drop intermediate columns
        .drop("_prev_timestamp", "_prev_latitude", "_prev_longitude", "_distance_km", "_hour", "_prev_device")
    )

    return df_features


def compute_statistical_features(df: DataFrame) -> DataFrame:
    """Compute running statistical features using windowed aggregations.

    Features computed:
        - amount_avg_7d: Approximate running average amount (uses session window approximation)
        - amount_zscore: Standardized spending deviation
        - tx_count_24h: Approximate 24h count via sliding window

    In streaming mode, true rolling windows over 7 days are not practical.
    We approximate using the available state within each micro-batch.
    """
    customer_window = (
        Window.partitionBy("customer_id")
        .orderBy("event_timestamp")
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )

    df_stats = (
        df
        .withColumn("_running_sum", F.sum("amount").over(customer_window))
        .withColumn("_running_count", F.count("*").over(customer_window))
        .withColumn(
            "amount_avg_7d",
            F.col("_running_sum") / F.col("_running_count"),
        )
        .withColumn(
            "_running_stddev",
            F.stddev("amount").over(customer_window),
        )
        .withColumn(
            "amount_zscore",
            F.when(
                (F.col("_running_stddev").isNotNull()) & (F.col("_running_stddev") > 0),
                (F.col("amount") - F.col("amount_avg_7d")) / F.col("_running_stddev"),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn("tx_count_24h", F.col("_running_count"))
        .drop("_running_sum", "_running_count", "_running_stddev")
    )

    return df_stats


def compute_merchant_risk(df: DataFrame) -> DataFrame:
    """Add merchant_risk_score based on historical fraud rate.

    In production this would be a lookup against a maintained table.
    For the streaming pipeline, we use a rule-based approximation where
    certain merchant categories carry higher baseline risk.
    """
    merchant_risk_map = {
        "online_gambling": 0.8,
        "crypto_exchange": 0.75,
        "wire_transfer": 0.7,
        "electronics": 0.5,
        "jewelry": 0.55,
        "travel": 0.3,
        "grocery": 0.05,
        "restaurant": 0.1,
        "gas_station": 0.15,
        "subscription": 0.1,
    }

    risk_expr = F.lit(0.2)  # default risk
    for category, score in merchant_risk_map.items():
        risk_expr = F.when(
            F.col("merchant_category") == category, F.lit(score)
        ).otherwise(risk_expr)

    return df.withColumn("merchant_risk_score", risk_expr)


def add_all_features(df: DataFrame) -> DataFrame:
    """Apply all feature transformations to a transaction DataFrame.

    This is the main entry point used by the streaming pipeline.
    Applies per-transaction features, statistical features, and merchant risk.

    Args:
        df: Streaming DataFrame with watermark on event_timestamp.

    Returns:
        DataFrame with all 10 features added.
    """
    logger.info("Computing fraud detection features...")

    df = compute_per_transaction_features(df)
    df = compute_statistical_features(df)
    df = compute_merchant_risk(df)

    # Set defaults for missing windowed features (will be populated in foreachBatch)
    if "tx_count_1h" not in df.columns:
        df = df.withColumn("tx_count_1h", F.lit(0).cast(T.LongType()))
    if "rapid_tx_count" not in df.columns:
        df = df.withColumn("rapid_tx_count", F.lit(0).cast(T.LongType()))

    return df
