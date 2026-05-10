"""Safe schema evolution utilities for Iceberg tables.

Provides helpers for common schema changes: adding columns, renaming
columns, widening types, and viewing schema history.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("schema_evolution")


def add_column(
    spark,
    table_name: str,
    column_name: str,
    data_type: str,
    comment: str = "",
    after: str | None = None,
) -> None:
    """Add a new column to an Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        column_name: Name of the new column.
        data_type: Spark SQL data type (e.g., 'STRING', 'DOUBLE', 'LONG').
        comment: Optional column comment.
        after: Optional column name to position after.
    """
    after_clause = f" AFTER {after}" if after else ""
    comment_clause = f" COMMENT '{comment}'" if comment else ""

    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {data_type}{comment_clause}{after_clause}"

    logger.info("Adding column: %s", sql)
    spark.sql(sql)
    logger.info("Column '%s' added to '%s'.", column_name, table_name)


def rename_column(spark, table_name: str, old_name: str, new_name: str) -> None:
    """Rename a column in an Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        old_name: Current column name.
        new_name: New column name.
    """
    sql = f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"

    logger.info("Renaming column: %s", sql)
    spark.sql(sql)
    logger.info("Column '%s' renamed to '%s' in '%s'.", old_name, new_name, table_name)


def widen_type(spark, table_name: str, column_name: str, new_type: str) -> None:
    """Widen a column's data type (e.g., INT → LONG, FLOAT → DOUBLE).

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        column_name: Column to widen.
        new_type: New, wider data type.
    """
    sql = f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_type}"

    logger.info("Widening type: %s", sql)
    spark.sql(sql)
    logger.info("Column '%s' type widened to '%s' in '%s'.", column_name, new_type, table_name)


def drop_column(spark, table_name: str, column_name: str) -> None:
    """Drop a column from an Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
        column_name: Column to drop.
    """
    sql = f"ALTER TABLE {table_name} DROP COLUMN {column_name}"

    logger.info("Dropping column: %s", sql)
    spark.sql(sql)
    logger.info("Column '%s' dropped from '%s'.", column_name, table_name)


def show_schema(spark, table_name: str) -> None:
    """Display the current schema of an Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
    """
    logger.info("Schema for %s:", table_name)
    spark.sql(f"DESCRIBE TABLE EXTENDED {table_name}").show(100, truncate=False)


def show_schema_history(spark, table_name: str) -> None:
    """Display the schema change history of an Iceberg table.

    Shows all snapshots where schema was modified.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified table name.
    """
    parts = table_name.split(".", 1)
    catalog = parts[0]
    rest = parts[1]

    logger.info("Schema history for %s:", table_name)

    # Show snapshots (includes schema changes)
    spark.sql(f"""
        SELECT snapshot_id, committed_at, operation, summary
        FROM {catalog}.{rest}.snapshots
        ORDER BY committed_at DESC
    """).show(50, truncate=False)

    # Show metadata log
    try:
        spark.sql(f"""
            SELECT * FROM {catalog}.{rest}.metadata_log_entries
            ORDER BY timestamp DESC
        """).show(20, truncate=False)
    except Exception:
        logger.info("Metadata log entries not available for this table.")


def apply_migration(spark, table_name: str, migration_name: str) -> None:
    """Apply a named migration to a table.

    This is a registry pattern for versioned schema changes.

    Args:
        spark: Active SparkSession.
        table_name: Table to migrate.
        migration_name: Migration identifier.
    """
    migrations = {
        "v2_add_risk_features": [
            ("model_version", "STRING", "ML model version used for scoring"),
            ("score_explanation", "STRING", "JSON explanation of score components"),
        ],
        "v3_add_compliance": [
            ("compliance_flag", "STRING", "Regulatory compliance status"),
            ("reporting_entity", "STRING", "Entity responsible for reporting"),
        ],
    }

    if migration_name not in migrations:
        logger.error("Unknown migration: %s. Available: %s", migration_name, list(migrations.keys()))
        return

    columns = migrations[migration_name]
    logger.info("Applying migration '%s' to '%s' (%d columns)...", migration_name, table_name, len(columns))

    for col_name, col_type, col_comment in columns:
        try:
            add_column(spark, table_name, col_name, col_type, col_comment)
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("Column '%s' already exists, skipping.", col_name)
            else:
                raise

    logger.info("Migration '%s' applied successfully.", migration_name)


def main() -> None:
    """Demonstrate schema evolution operations."""
    spark = get_spark_session(app_name="SchemaEvolutionDemo")

    logger.info("=" * 50)
    logger.info("  Schema Evolution Demo")
    logger.info("=" * 50)

    table = "nessie.silver.enriched_transactions"

    try:
        show_schema(spark, table)
        show_schema_history(spark, table)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
