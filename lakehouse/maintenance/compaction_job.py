"""Iceberg table compaction job.

Rewrites small data files into optimally sized files (~128MB target)
to improve scan performance. Intended to be scheduled via Airflow daily.
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("compaction_job")

# Target file size in bytes (128MB)
TARGET_FILE_SIZE_BYTES = 128 * 1024 * 1024

# Tables to compact
TABLES = [
    "nessie.bronze.raw_transactions",
    "nessie.silver.enriched_transactions",
    "nessie.gold.fraud_metrics",
    "nessie.gold.customer_risk_profiles",
    "nessie.gold.merchant_risk_scores",
]


def compact_table(spark, table_name: str) -> dict:
    """Run compaction (rewrite data files) on a single Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified Iceberg table name.

    Returns:
        Dict with compaction results.
    """
    logger.info("Compacting table: %s", table_name)
    start = time.time()

    try:
        result = spark.sql(f"""
            CALL nessie.system.rewrite_data_files(
                table => '{table_name}',
                options => map(
                    'target-file-size-bytes', '{TARGET_FILE_SIZE_BYTES}',
                    'min-file-size-bytes', '{int(TARGET_FILE_SIZE_BYTES * 0.75)}',
                    'max-file-size-bytes', '{int(TARGET_FILE_SIZE_BYTES * 1.8)}'
                )
            )
        """)

        rows = result.collect()
        elapsed = time.time() - start

        stats = {
            "table": table_name,
            "duration_sec": round(elapsed, 2),
            "rewritten_data_files_count": rows[0]["rewritten_data_files_count"] if rows else 0,
            "added_data_files_count": rows[0]["added_data_files_count"] if rows else 0,
        }

        logger.info(
            "Compacted %s: %d files rewritten → %d files in %.2fs",
            table_name,
            stats["rewritten_data_files_count"],
            stats["added_data_files_count"],
            elapsed,
        )
        return stats

    except Exception as e:
        elapsed = time.time() - start
        logger.error("Compaction failed for %s after %.2fs: %s", table_name, elapsed, e)
        return {"table": table_name, "error": str(e), "duration_sec": round(elapsed, 2)}


def run_compaction(tables: list[str] | None = None) -> list[dict]:
    """Run compaction on all specified tables.

    Args:
        tables: List of table names. Defaults to TABLES constant.

    Returns:
        List of compaction result dicts.
    """
    spark = get_spark_session(app_name="IcebergCompaction")
    target_tables = tables or TABLES
    results = []

    for table in target_tables:
        result = compact_table(spark, table)
        results.append(result)

    spark.stop()
    return results


def main() -> None:
    """Entry point for standalone execution."""
    logger.info("=" * 50)
    logger.info("  Iceberg Compaction Job")
    logger.info("=" * 50)

    results = run_compaction()

    logger.info("Compaction Summary:")
    for r in results:
        if "error" in r:
            logger.error("  %s: FAILED (%s)", r["table"], r["error"])
        else:
            logger.info(
                "  %s: %d → %d files (%.2fs)",
                r["table"],
                r["rewritten_data_files_count"],
                r["added_data_files_count"],
                r["duration_sec"],
            )


if __name__ == "__main__":
    main()
