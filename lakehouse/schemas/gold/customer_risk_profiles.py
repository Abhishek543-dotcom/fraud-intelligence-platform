"""Gold layer: customer_risk_profiles table."""

import logging

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

TABLE_NAME = "nessie.gold.customer_risk_profiles"


def create_table(spark: SparkSession) -> None:
    """Create the gold customer_risk_profiles Iceberg table."""
    logger.info("Creating gold table: %s", TABLE_NAME)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            customer_id             STRING      COMMENT 'Customer identifier (primary key)',
            total_transactions      LONG        COMMENT 'Lifetime transaction count',
            fraud_count             LONG        COMMENT 'Number of flagged fraud transactions',
            total_amount            DOUBLE      COMMENT 'Lifetime transaction amount',
            avg_fraud_score         DOUBLE      COMMENT 'Average fraud score across all transactions',
            max_fraud_score         DOUBLE      COMMENT 'Highest fraud score ever observed',
            last_fraud_timestamp    TIMESTAMP   COMMENT 'Timestamp of most recent flagged transaction',
            risk_level              STRING      COMMENT 'Derived risk level: LOW, MEDIUM, HIGH, CRITICAL',
            updated_at              TIMESTAMP   COMMENT 'Last profile update timestamp'
        )
        USING iceberg
        TBLPROPERTIES (
            'format-version' = '2',
            'write.merge.mode' = 'merge-on-read'
        )
    """)

    logger.info("Gold table '%s' ready.", TABLE_NAME)


def refresh_profiles(spark: SparkSession) -> None:
    """Rebuild customer risk profiles from the silver layer.

    Aggregates all enriched transactions per customer and classifies
    risk level based on fraud rate and score thresholds.
    """
    silver_table = "nessie.silver.enriched_transactions"

    spark.sql(f"""
        MERGE INTO {TABLE_NAME} AS target
        USING (
            SELECT
                customer_id,
                COUNT(*) AS total_transactions,
                SUM(CASE WHEN fraud_score > 0.7 THEN 1 ELSE 0 END) AS fraud_count,
                SUM(amount) AS total_amount,
                AVG(fraud_score) AS avg_fraud_score,
                MAX(fraud_score) AS max_fraud_score,
                MAX(CASE WHEN fraud_score > 0.7 THEN event_timestamp END) AS last_fraud_timestamp,
                CASE
                    WHEN AVG(fraud_score) > 0.6 THEN 'CRITICAL'
                    WHEN AVG(fraud_score) > 0.4 THEN 'HIGH'
                    WHEN AVG(fraud_score) > 0.2 THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS risk_level,
                current_timestamp() AS updated_at
            FROM {silver_table}
            GROUP BY customer_id
        ) AS source
        ON target.customer_id = source.customer_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    logger.info("Customer risk profiles refreshed.")


def get_table_name() -> str:
    return TABLE_NAME
