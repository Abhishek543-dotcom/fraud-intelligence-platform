"""Iceberg table writer for Spark Structured Streaming foreachBatch sink.

Handles writing micro-batches to bronze, silver, and gold Iceberg tables
with schema evolution, deduplication, and partitioning.
"""

import logging
import time
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

logger = logging.getLogger(__name__)

BRONZE_TABLE = "nessie.bronze.raw_transactions"
SILVER_TABLE = "nessie.silver.enriched_transactions"


def write_to_bronze(batch_df: DataFrame, batch_id: int) -> None:
    """Write a micro-batch to the bronze Iceberg table (append only, no dedup).

    Args:
        batch_df: The micro-batch DataFrame from Spark Structured Streaming.
        batch_id: The micro-batch identifier.
    """
    start = time.time()
    record_count = batch_df.count()

    if record_count == 0:
        logger.info("Bronze batch %d: empty, skipping.", batch_id)
        return

    df_bronze = (
        batch_df
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("event_date", F.to_date("event_timestamp"))
        .withColumn("batch_id", F.lit(batch_id))
    )

    df_bronze.writeTo(BRONZE_TABLE).option(
        "merge-schema", "true"
    ).append()

    elapsed = time.time() - start
    logger.info(
        "Bronze batch %d: wrote %d records in %.2fs",
        batch_id,
        record_count,
        elapsed,
    )


def write_to_silver(batch_df: DataFrame, batch_id: int) -> None:
    """Write enriched, deduplicated transactions to the silver Iceberg table.

    Uses MERGE INTO for upsert semantics: if transaction_id already exists,
    update with newer data; otherwise insert.

    Args:
        batch_df: The micro-batch DataFrame with computed features.
        batch_id: The micro-batch identifier.
    """
    start = time.time()
    record_count = batch_df.count()

    if record_count == 0:
        logger.info("Silver batch %d: empty, skipping.", batch_id)
        return

    spark = batch_df.sparkSession

    df_silver = (
        batch_df
        .withColumn("processing_timestamp", F.current_timestamp())
        .withColumn("event_date", F.to_date("event_timestamp"))
    )

    # Deduplicate within the micro-batch by keeping the latest per transaction_id
    df_deduped = (
        df_silver
        .withColumn(
            "_rank",
            F.row_number().over(
                F.Window.partitionBy("transaction_id").orderBy(F.col("event_timestamp").desc())
            ),
        )
        .filter(F.col("_rank") == 1)
        .drop("_rank")
    )

    # Register as temp view for MERGE INTO SQL
    df_deduped.createOrReplaceTempView("_silver_batch")

    merge_sql = f"""
    MERGE INTO {SILVER_TABLE} AS target
    USING _silver_batch AS source
    ON target.transaction_id = source.transaction_id
    WHEN MATCHED AND source.event_timestamp > target.event_timestamp THEN
        UPDATE SET *
    WHEN NOT MATCHED THEN
        INSERT *
    """

    try:
        spark.sql(merge_sql)
        elapsed = time.time() - start
        logger.info(
            "Silver batch %d: merged %d records (deduped from %d) in %.2fs",
            batch_id,
            df_deduped.count(),
            record_count,
            elapsed,
        )
    except Exception as e:
        logger.error("Silver batch %d: MERGE failed: %s. Falling back to append.", batch_id, e)
        df_deduped.writeTo(SILVER_TABLE).option("merge-schema", "true").append()


def write_to_gold_fraud_metrics(batch_df: DataFrame, batch_id: int) -> None:
    """Aggregate and write hourly fraud metrics to the gold layer.

    Args:
        batch_df: Micro-batch DataFrame with fraud_score column.
        batch_id: Micro-batch identifier.
    """
    record_count = batch_df.count()
    if record_count == 0:
        return

    metrics_df = (
        batch_df
        .withColumn("metric_hour", F.date_trunc("hour", "event_timestamp"))
        .groupBy("metric_hour")
        .agg(
            F.count("*").alias("total_transactions"),
            F.sum(F.when(F.col("fraud_score") > 0.7, 1).otherwise(0)).alias("fraud_count"),
            F.sum(
                F.when(F.col("fraud_score") > 0.7, F.col("amount")).otherwise(0)
            ).alias("total_amount_blocked"),
            F.avg("fraud_score").alias("avg_fraud_score"),
            F.max("fraud_score").alias("max_fraud_score"),
            F.sum("amount").alias("total_amount_processed"),
        )
        .withColumn("updated_at", F.current_timestamp())
    )

    gold_table = "nessie.gold.fraud_metrics"
    metrics_df.createOrReplaceTempView("_gold_metrics_batch")

    spark = batch_df.sparkSession
    merge_sql = f"""
    MERGE INTO {gold_table} AS target
    USING _gold_metrics_batch AS source
    ON target.metric_hour = source.metric_hour
    WHEN MATCHED THEN
        UPDATE SET
            total_transactions = target.total_transactions + source.total_transactions,
            fraud_count = target.fraud_count + source.fraud_count,
            total_amount_blocked = target.total_amount_blocked + source.total_amount_blocked,
            avg_fraud_score = (target.avg_fraud_score + source.avg_fraud_score) / 2,
            max_fraud_score = GREATEST(target.max_fraud_score, source.max_fraud_score),
            total_amount_processed = target.total_amount_processed + source.total_amount_processed,
            updated_at = source.updated_at
    WHEN NOT MATCHED THEN
        INSERT *
    """

    try:
        spark.sql(merge_sql)
        logger.info("Gold fraud_metrics batch %d: aggregated %d records.", batch_id, record_count)
    except Exception as e:
        logger.error("Gold fraud_metrics batch %d failed: %s. Appending instead.", batch_id, e)
        metrics_df.writeTo(gold_table).option("merge-schema", "true").append()


def ensure_tables_exist(spark: SparkSession) -> None:
    """Create bronze, silver, and gold Iceberg tables if they don't exist.

    Args:
        spark: Active SparkSession with Nessie catalog configured.
    """
    logger.info("Ensuring Iceberg tables exist...")

    # Bronze: raw transactions, partitioned by event_date
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {BRONZE_TABLE} (
            transaction_id STRING,
            customer_id STRING,
            amount DOUBLE,
            currency STRING,
            merchant_id STRING,
            merchant_name STRING,
            merchant_category STRING,
            transaction_type STRING,
            channel STRING,
            device_id STRING,
            ip_address STRING,
            latitude DOUBLE,
            longitude DOUBLE,
            city STRING,
            country STRING,
            is_fraud BOOLEAN,
            event_timestamp TIMESTAMP,
            event_date DATE,
            ingestion_timestamp TIMESTAMP,
            batch_id LONG
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
    """)

    # Silver: enriched transactions with features
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {SILVER_TABLE} (
            transaction_id STRING,
            customer_id STRING,
            amount DOUBLE,
            currency STRING,
            merchant_id STRING,
            merchant_name STRING,
            merchant_category STRING,
            transaction_type STRING,
            channel STRING,
            device_id STRING,
            ip_address STRING,
            latitude DOUBLE,
            longitude DOUBLE,
            city STRING,
            country STRING,
            is_fraud BOOLEAN,
            event_timestamp TIMESTAMP,
            event_date DATE,
            tx_count_1h LONG,
            tx_count_24h LONG,
            amount_avg_7d DOUBLE,
            amount_zscore DOUBLE,
            geo_velocity_kmh DOUBLE,
            merchant_risk_score DOUBLE,
            device_consistency DOUBLE,
            time_since_last_tx LONG,
            is_unusual_hour BOOLEAN,
            rapid_tx_count LONG,
            fraud_score DOUBLE,
            processing_timestamp TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp), transaction_type)
    """)

    # Gold: fraud metrics (hourly aggregates)
    spark.sql("""
        CREATE TABLE IF NOT EXISTS nessie.gold.fraud_metrics (
            metric_hour TIMESTAMP,
            total_transactions LONG,
            fraud_count LONG,
            total_amount_blocked DOUBLE,
            avg_fraud_score DOUBLE,
            max_fraud_score DOUBLE,
            total_amount_processed DOUBLE,
            updated_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(metric_hour))
    """)

    # Gold: customer risk profiles
    spark.sql("""
        CREATE TABLE IF NOT EXISTS nessie.gold.customer_risk_profiles (
            customer_id STRING,
            total_transactions LONG,
            fraud_count LONG,
            total_amount DOUBLE,
            avg_fraud_score DOUBLE,
            max_fraud_score DOUBLE,
            last_fraud_timestamp TIMESTAMP,
            risk_level STRING,
            updated_at TIMESTAMP
        )
        USING iceberg
    """)

    # Gold: merchant risk scores
    spark.sql("""
        CREATE TABLE IF NOT EXISTS nessie.gold.merchant_risk_scores (
            merchant_id STRING,
            merchant_name STRING,
            merchant_category STRING,
            total_transactions LONG,
            fraud_count LONG,
            fraud_rate DOUBLE,
            avg_fraud_score DOUBLE,
            total_amount_blocked DOUBLE,
            risk_tier STRING,
            updated_at TIMESTAMP
        )
        USING iceberg
    """)

    logger.info("All Iceberg tables verified/created.")
