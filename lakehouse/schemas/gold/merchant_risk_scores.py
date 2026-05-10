"""Gold layer: merchant_risk_scores table."""

import logging

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

TABLE_NAME = "nessie.gold.merchant_risk_scores"


def create_table(spark: SparkSession) -> None:
    """Create the gold merchant_risk_scores Iceberg table."""
    logger.info("Creating gold table: %s", TABLE_NAME)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            merchant_id             STRING      COMMENT 'Merchant identifier (primary key)',
            merchant_name           STRING      COMMENT 'Merchant display name',
            merchant_category       STRING      COMMENT 'Merchant category code',
            total_transactions      LONG        COMMENT 'Total transactions at this merchant',
            fraud_count             LONG        COMMENT 'Number of fraudulent transactions',
            fraud_rate              DOUBLE      COMMENT 'Fraction of transactions flagged as fraud',
            avg_fraud_score         DOUBLE      COMMENT 'Average fraud score at this merchant',
            total_amount_blocked    DOUBLE      COMMENT 'Total monetary value blocked',
            risk_tier               STRING      COMMENT 'Risk tier: SAFE, WATCH, ELEVATED, HIGH_RISK, BLOCKED',
            updated_at              TIMESTAMP   COMMENT 'Last update timestamp'
        )
        USING iceberg
        TBLPROPERTIES (
            'format-version' = '2',
            'write.merge.mode' = 'merge-on-read'
        )
    """)

    logger.info("Gold table '%s' ready.", TABLE_NAME)


def refresh_scores(spark: SparkSession) -> None:
    """Rebuild merchant risk scores from the silver layer."""
    silver_table = "nessie.silver.enriched_transactions"

    spark.sql(f"""
        MERGE INTO {TABLE_NAME} AS target
        USING (
            SELECT
                merchant_id,
                FIRST(merchant_name) AS merchant_name,
                FIRST(merchant_category) AS merchant_category,
                COUNT(*) AS total_transactions,
                SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) AS fraud_count,
                SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*) AS fraud_rate,
                AVG(fraud_score) AS avg_fraud_score,
                SUM(CASE WHEN fraud_score > 0.7 THEN amount ELSE 0 END) AS total_amount_blocked,
                CASE
                    WHEN SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*) > 0.3 THEN 'BLOCKED'
                    WHEN SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*) > 0.15 THEN 'HIGH_RISK'
                    WHEN SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*) > 0.05 THEN 'ELEVATED'
                    WHEN SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*) > 0.01 THEN 'WATCH'
                    ELSE 'SAFE'
                END AS risk_tier,
                current_timestamp() AS updated_at
            FROM {silver_table}
            GROUP BY merchant_id
        ) AS source
        ON target.merchant_id = source.merchant_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    logger.info("Merchant risk scores refreshed.")


def get_table_name() -> str:
    return TABLE_NAME
