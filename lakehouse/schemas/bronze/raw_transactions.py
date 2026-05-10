"""Bronze layer: raw_transactions table schema and creation.

The bronze layer stores raw, unprocessed transaction events exactly as
received from Kafka. Partitioned by event date for efficient time-range
queries. No deduplication at this layer.
"""

import logging

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

TABLE_NAME = "nessie.bronze.raw_transactions"


def create_table(spark: SparkSession) -> None:
    """Create the bronze raw_transactions Iceberg table if it doesn't exist.

    Table properties:
        - Partitioned by days(event_timestamp) for efficient date range scans
        - Write mode: append only (no dedup)
        - Format version 2 for row-level deletes support
    """
    logger.info("Creating bronze table: %s", TABLE_NAME)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            transaction_id      STRING      COMMENT 'Unique transaction identifier (UUID)',
            customer_id         STRING      COMMENT 'Customer identifier',
            amount              DOUBLE      COMMENT 'Transaction amount in specified currency',
            currency            STRING      COMMENT 'ISO 4217 currency code',
            merchant_id         STRING      COMMENT 'Merchant identifier',
            merchant_name       STRING      COMMENT 'Merchant display name',
            merchant_category   STRING      COMMENT 'Merchant category code',
            transaction_type    STRING      COMMENT 'Transaction type: purchase, transfer, withdrawal, etc.',
            channel             STRING      COMMENT 'Transaction channel: online, pos, atm, mobile',
            device_id           STRING      COMMENT 'Device fingerprint identifier',
            ip_address          STRING      COMMENT 'Source IP address',
            latitude            DOUBLE      COMMENT 'Transaction location latitude',
            longitude           DOUBLE      COMMENT 'Transaction location longitude',
            city                STRING      COMMENT 'Transaction city',
            country             STRING      COMMENT 'Transaction country (ISO 3166-1 alpha-2)',
            is_fraud            BOOLEAN     COMMENT 'Ground truth fraud label (for training)',
            event_timestamp     TIMESTAMP   COMMENT 'Event time from source system',
            event_date          DATE        COMMENT 'Derived: date of event_timestamp',
            ingestion_timestamp TIMESTAMP   COMMENT 'Time when record was written to bronze',
            batch_id            LONG        COMMENT 'Spark streaming micro-batch ID'
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp))
        TBLPROPERTIES (
            'format-version' = '2',
            'write.metadata.delete-after-commit.enabled' = 'true',
            'write.metadata.previous-versions-max' = '50',
            'commit.retry.num-retries' = '4'
        )
    """)

    logger.info("Bronze table '%s' ready.", TABLE_NAME)


def get_table_name() -> str:
    """Return the fully qualified bronze table name."""
    return TABLE_NAME
