"""Gold layer: fraud_metrics hourly aggregate table."""

import logging

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

TABLE_NAME = "nessie.gold.fraud_metrics"


def create_table(spark: SparkSession) -> None:
    """Create the gold fraud_metrics Iceberg table."""
    logger.info("Creating gold table: %s", TABLE_NAME)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            metric_hour             TIMESTAMP   COMMENT 'Hour bucket for aggregation',
            total_transactions      LONG        COMMENT 'Total transactions in this hour',
            fraud_count             LONG        COMMENT 'Number of flagged fraud transactions',
            total_amount_blocked    DOUBLE      COMMENT 'Sum of amounts on fraudulent transactions',
            avg_fraud_score         DOUBLE      COMMENT 'Average fraud score across all transactions',
            max_fraud_score         DOUBLE      COMMENT 'Maximum fraud score observed',
            total_amount_processed  DOUBLE      COMMENT 'Sum of all transaction amounts',
            updated_at              TIMESTAMP   COMMENT 'Last update timestamp'
        )
        USING iceberg
        PARTITIONED BY (days(metric_hour))
        TBLPROPERTIES (
            'format-version' = '2',
            'write.merge.mode' = 'merge-on-read'
        )
    """)

    logger.info("Gold table '%s' ready.", TABLE_NAME)


def get_table_name() -> str:
    return TABLE_NAME
