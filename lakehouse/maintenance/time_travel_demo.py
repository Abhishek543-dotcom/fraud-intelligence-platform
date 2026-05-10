"""Iceberg time travel demonstration.

Shows how to query historical states of tables using Iceberg's
snapshot and timestamp-based time travel capabilities.
"""

import logging
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("time_travel_demo")


def list_snapshots(spark, table_name: str) -> None:
    """List all available snapshots for a table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified Iceberg table name (e.g., 'nessie.bronze.raw_transactions').
    """
    # Extract the part after the catalog name for metadata table access
    parts = table_name.split(".", 1)
    catalog = parts[0]
    rest = parts[1] if len(parts) > 1 else table_name

    logger.info("Snapshots for %s:", table_name)

    df = spark.sql(f"SELECT * FROM {catalog}.{rest}.snapshots ORDER BY committed_at DESC")
    df.show(truncate=False)

    logger.info("Total snapshots: %d", df.count())


def query_as_of_timestamp(spark, table_name: str, timestamp: str):
    """Query a table as it existed at a specific timestamp.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        timestamp: ISO-format timestamp string (e.g., '2024-01-15 10:00:00').

    Returns:
        DataFrame representing the table state at that time.
    """
    logger.info("Querying %s AS OF TIMESTAMP '%s'", table_name, timestamp)

    df = spark.sql(f"""
        SELECT * FROM {table_name}
        TIMESTAMP AS OF '{timestamp}'
    """)

    logger.info("Result row count: %d", df.count())
    return df


def query_as_of_version(spark, table_name: str, snapshot_id: int):
    """Query a table at a specific snapshot version.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        snapshot_id: Iceberg snapshot ID.

    Returns:
        DataFrame representing the table at that snapshot.
    """
    logger.info("Querying %s VERSION AS OF %d", table_name, snapshot_id)

    df = spark.sql(f"""
        SELECT * FROM {table_name}
        VERSION AS OF {snapshot_id}
    """)

    logger.info("Result row count: %d", df.count())
    return df


def compare_snapshots(spark, table_name: str, from_snapshot: int, to_snapshot: int):
    """Show records that changed between two snapshots.

    Uses Iceberg's incremental read to find new/changed records.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        from_snapshot: Earlier snapshot ID.
        to_snapshot: Later snapshot ID.

    Returns:
        DataFrame of changed records.
    """
    logger.info(
        "Comparing snapshots for %s: %d → %d",
        table_name,
        from_snapshot,
        to_snapshot,
    )

    df = (
        spark.read
        .format("iceberg")
        .option("start-snapshot-id", str(from_snapshot))
        .option("end-snapshot-id", str(to_snapshot))
        .load(table_name)
    )

    logger.info("Records changed between snapshots: %d", df.count())
    return df


def show_table_history(spark, table_name: str) -> None:
    """Display the full history of a table including schema changes.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
    """
    parts = table_name.split(".", 1)
    catalog = parts[0]
    rest = parts[1]

    logger.info("History for %s:", table_name)

    history_df = spark.sql(f"SELECT * FROM {catalog}.{rest}.history ORDER BY made_current_at DESC")
    history_df.show(truncate=False)


def demo_main() -> None:
    """Run the time travel demonstration."""
    spark = get_spark_session(app_name="TimeTravelDemo")
    table = "nessie.bronze.raw_transactions"

    logger.info("=" * 50)
    logger.info("  Iceberg Time Travel Demo")
    logger.info("=" * 50)

    try:
        # 1. List snapshots
        list_snapshots(spark, table)

        # 2. Show table history
        show_table_history(spark, table)

        # 3. Query as of 1 hour ago
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            df_past = query_as_of_timestamp(spark, table, one_hour_ago)
            df_past.show(5, truncate=False)
        except Exception as e:
            logger.info("No snapshot available for 1 hour ago: %s", e)

        # 4. Show current state
        current_df = spark.sql(f"SELECT COUNT(*) as current_count FROM {table}")
        current_df.show()

        logger.info("Time travel demo complete.")

    finally:
        spark.stop()


if __name__ == "__main__":
    demo_main()
