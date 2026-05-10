"""Multi-stream correlation via stream-stream join.

Joins the raw transaction stream with enrichment data streams
(e.g., device fingerprints, customer profiles) to produce a
richer view for fraud detection.
"""

import logging
import os
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("stream_stream_join")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")

TRANSACTION_SCHEMA = T.StructType([
    T.StructField("transaction_id", T.StringType(), False),
    T.StructField("customer_id", T.StringType(), False),
    T.StructField("amount", T.DoubleType(), False),
    T.StructField("currency", T.StringType(), True),
    T.StructField("merchant_id", T.StringType(), True),
    T.StructField("merchant_name", T.StringType(), True),
    T.StructField("merchant_category", T.StringType(), True),
    T.StructField("event_timestamp", T.TimestampType(), False),
])

ENRICHMENT_SCHEMA = T.StructType([
    T.StructField("transaction_id", T.StringType(), False),
    T.StructField("device_fingerprint", T.StringType(), True),
    T.StructField("ip_risk_score", T.DoubleType(), True),
    T.StructField("customer_tenure_days", T.IntegerType(), True),
    T.StructField("customer_segment", T.StringType(), True),
    T.StructField("enrichment_timestamp", T.TimestampType(), False),
])


def read_transaction_stream(spark: SparkSession) -> DataFrame:
    """Read raw transaction stream from Kafka."""
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", "transactions_raw")
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    return (
        raw
        .select(F.from_json(F.col("value").cast("string"), TRANSACTION_SCHEMA).alias("tx"))
        .select("tx.*")
        .withWatermark("event_timestamp", "30 seconds")
    )


def read_enrichment_stream(spark: SparkSession) -> DataFrame:
    """Read enrichment data stream from Kafka."""
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", "transactions_enriched")
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    return (
        raw
        .select(F.from_json(F.col("value").cast("string"), ENRICHMENT_SCHEMA).alias("enrich"))
        .select("enrich.*")
        .withWatermark("enrichment_timestamp", "1 minute")
    )


def join_streams(
    tx_stream: DataFrame,
    enrich_stream: DataFrame,
) -> DataFrame:
    """Perform a stream-stream join between transactions and enrichment data.

    Uses an interval join condition: the enrichment event must arrive within
    a 2-minute window of the transaction event.

    Args:
        tx_stream: Transaction stream with watermark on event_timestamp.
        enrich_stream: Enrichment stream with watermark on enrichment_timestamp.

    Returns:
        Joined DataFrame with transaction + enrichment columns.
    """
    joined = tx_stream.join(
        enrich_stream,
        on=(
            (tx_stream.transaction_id == enrich_stream.transaction_id)
            & (
                enrich_stream.enrichment_timestamp.between(
                    tx_stream.event_timestamp,
                    tx_stream.event_timestamp + F.expr("INTERVAL 2 MINUTES"),
                )
            )
        ),
        how="leftOuter",
    )

    # Select and rename to avoid ambiguity
    result = joined.select(
        tx_stream.transaction_id,
        tx_stream.customer_id,
        tx_stream.amount,
        tx_stream.currency,
        tx_stream.merchant_id,
        tx_stream.merchant_name,
        tx_stream.merchant_category,
        tx_stream.event_timestamp,
        enrich_stream.device_fingerprint,
        enrich_stream.ip_risk_score,
        enrich_stream.customer_tenure_days,
        enrich_stream.customer_segment,
    )

    return result


def write_joined_to_kafka(joined_df: DataFrame) -> None:
    """Write the joined stream to the transactions_enriched topic."""
    output = (
        joined_df
        .withColumn("value", F.to_json(F.struct("*")))
        .withColumn("key", F.col("transaction_id"))
        .select("key", "value")
    )

    query = (
        output.writeStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("topic", "transactions_enriched")
        .option("checkpointLocation", "s3a://spark-checkpoints/stream-stream-join/")
        .trigger(processingTime="15 seconds")
        .queryName("stream_stream_join")
        .start()
    )

    logger.info("Stream-stream join query started: %s", query.id)
    query.awaitTermination()


def main() -> None:
    """Entry point for stream-stream join job."""
    spark = get_spark_session(app_name="StreamStreamJoin")

    try:
        tx_stream = read_transaction_stream(spark)
        enrich_stream = read_enrichment_stream(spark)
        joined = join_streams(tx_stream, enrich_stream)
        write_joined_to_kafka(joined)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
