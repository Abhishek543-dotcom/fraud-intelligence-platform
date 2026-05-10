"""Silver layer: enriched_transactions table schema and creation.

The silver layer stores validated, deduplicated transactions enriched
with computed features. Uses MERGE for upserts by transaction_id.
"""

import logging

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

TABLE_NAME = "nessie.silver.enriched_transactions"


def create_table(spark: SparkSession) -> None:
    """Create the silver enriched_transactions Iceberg table.

    Table properties:
        - Partitioned by days(event_timestamp) and transaction_type
        - Schema evolution enabled
        - Format version 2 for merge support
    """
    logger.info("Creating silver table: %s", TABLE_NAME)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            transaction_id          STRING      COMMENT 'Unique transaction identifier (UUID)',
            customer_id             STRING      COMMENT 'Customer identifier',
            amount                  DOUBLE      COMMENT 'Transaction amount',
            currency                STRING      COMMENT 'ISO 4217 currency code',
            merchant_id             STRING      COMMENT 'Merchant identifier',
            merchant_name           STRING      COMMENT 'Merchant display name',
            merchant_category       STRING      COMMENT 'Merchant category code',
            transaction_type        STRING      COMMENT 'Transaction type',
            channel                 STRING      COMMENT 'Transaction channel',
            device_id               STRING      COMMENT 'Device fingerprint',
            ip_address              STRING      COMMENT 'Source IP address',
            latitude                DOUBLE      COMMENT 'Location latitude',
            longitude               DOUBLE      COMMENT 'Location longitude',
            city                    STRING      COMMENT 'Transaction city',
            country                 STRING      COMMENT 'Transaction country',
            is_fraud                BOOLEAN     COMMENT 'Ground truth fraud label',
            event_timestamp         TIMESTAMP   COMMENT 'Original event time',
            event_date              DATE        COMMENT 'Derived event date',
            -- Computed features
            tx_count_1h             LONG        COMMENT 'Transaction count in 1-hour window',
            tx_count_24h            LONG        COMMENT 'Transaction count in 24-hour window',
            amount_avg_7d           DOUBLE      COMMENT 'Rolling 7-day average amount',
            amount_zscore           DOUBLE      COMMENT 'Z-score of amount vs running stats',
            geo_velocity_kmh        DOUBLE      COMMENT 'Travel speed from last transaction (km/h)',
            merchant_risk_score     DOUBLE      COMMENT 'Merchant fraud risk score [0, 1]',
            device_consistency      DOUBLE      COMMENT '1.0=known device, 0.0=new device',
            time_since_last_tx      LONG        COMMENT 'Seconds since previous transaction',
            is_unusual_hour         BOOLEAN     COMMENT 'True if transaction outside normal hours',
            rapid_tx_count          LONG        COMMENT 'Transaction count in last 5 minutes',
            fraud_score             DOUBLE      COMMENT 'Composite fraud risk score [0, 1]',
            processing_timestamp    TIMESTAMP   COMMENT 'Time when features were computed'
        )
        USING iceberg
        PARTITIONED BY (days(event_timestamp), transaction_type)
        TBLPROPERTIES (
            'format-version' = '2',
            'write.merge.mode' = 'merge-on-read',
            'write.update.mode' = 'merge-on-read',
            'write.delete.mode' = 'merge-on-read',
            'write.metadata.delete-after-commit.enabled' = 'true',
            'write.metadata.previous-versions-max' = '100'
        )
    """)

    logger.info("Silver table '%s' ready.", TABLE_NAME)


def get_table_name() -> str:
    """Return the fully qualified silver table name."""
    return TABLE_NAME
