"""Expire old Iceberg snapshots to reclaim storage.

Removes snapshots older than a configurable threshold while keeping
a minimum number of recent snapshots for safety.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from lakehouse.catalog.spark_iceberg_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("expire_snapshots")

TABLES = [
    "nessie.bronze.raw_transactions",
    "nessie.silver.enriched_transactions",
    "nessie.gold.fraud_metrics",
    "nessie.gold.customer_risk_profiles",
    "nessie.gold.merchant_risk_scores",
]

DEFAULT_RETENTION_DAYS = 7
MIN_SNAPSHOTS_TO_KEEP = 10


def expire_snapshots_for_table(
    spark,
    table_name: str,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    min_snapshots: int = MIN_SNAPSHOTS_TO_KEEP,
) -> dict:
    """Expire old snapshots for a single Iceberg table.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified Iceberg table name.
        retention_days: Keep snapshots newer than this many days.
        min_snapshots: Always keep at least this many snapshots.

    Returns:
        Dict with expiration results.
    """
    logger.info("Expiring snapshots for: %s (retention=%dd, min_keep=%d)", table_name, retention_days, min_snapshots)
    start = time.time()

    cutoff = datetime.now() - timedelta(days=retention_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    try:
        # List current snapshots
        snapshots_df = spark.sql(f"SELECT * FROM nessie.{table_name.split('.', 1)[1]}.snapshots")
        total_snapshots = snapshots_df.count()

        if total_snapshots <= min_snapshots:
            logger.info(
                "Table %s has %d snapshots (min=%d). Skipping expiration.",
                table_name,
                total_snapshots,
                min_snapshots,
            )
            return {
                "table": table_name,
                "snapshots_before": total_snapshots,
                "expired": 0,
                "skipped": True,
            }

        # Expire snapshots
        result = spark.sql(f"""
            CALL nessie.system.expire_snapshots(
                table => '{table_name}',
                older_than => TIMESTAMP '{cutoff_str}',
                retain_last => {min_snapshots}
            )
        """)

        rows = result.collect()
        elapsed = time.time() - start

        expired_count = rows[0]["deleted_data_files_count"] if rows else 0

        stats = {
            "table": table_name,
            "snapshots_before": total_snapshots,
            "expired_data_files": expired_count,
            "retention_cutoff": cutoff_str,
            "duration_sec": round(elapsed, 2),
        }

        logger.info(
            "Expired snapshots for %s: %d data files cleaned in %.2fs",
            table_name,
            expired_count,
            elapsed,
        )
        return stats

    except Exception as e:
        elapsed = time.time() - start
        logger.error("Snapshot expiration failed for %s: %s", table_name, e)
        return {"table": table_name, "error": str(e), "duration_sec": round(elapsed, 2)}


def run_expiration(
    tables: list[str] | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[dict]:
    """Run snapshot expiration on all specified tables.

    Args:
        tables: Table names to process. Defaults to TABLES.
        retention_days: Keep snapshots newer than this.

    Returns:
        List of result dicts.
    """
    spark = get_spark_session(app_name="IcebergSnapshotExpiration")
    target_tables = tables or TABLES
    results = []

    for table in target_tables:
        result = expire_snapshots_for_table(spark, table, retention_days)
        results.append(result)

    spark.stop()
    return results


def main() -> None:
    """Entry point for standalone execution."""
    logger.info("=" * 50)
    logger.info("  Iceberg Snapshot Expiration Job")
    logger.info("=" * 50)

    results = run_expiration()

    logger.info("Expiration Summary:")
    for r in results:
        if "error" in r:
            logger.error("  %s: FAILED (%s)", r["table"], r["error"])
        elif r.get("skipped"):
            logger.info("  %s: SKIPPED (only %d snapshots)", r["table"], r["snapshots_before"])
        else:
            logger.info(
                "  %s: %d data files expired (%.2fs)",
                r["table"],
                r["expired_data_files"],
                r["duration_sec"],
            )


if __name__ == "__main__":
    main()
