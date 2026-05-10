"""Iceberg table maintenance DAG — compaction, snapshot expiry, orphan cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def compact_small_files(**context):
    """Compact small Iceberg data files into larger ones for better read performance."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    tables = ["fraud_db.transactions", "fraud_db.fraud_alerts", "fraud_db.enriched_transactions"]

    for table in tables:
        try:
            spark.sql(f"CALL nessie.system.rewrite_data_files(table => '{table}')")
        except Exception as e:
            print(f"Compaction failed for {table}: {e}")

    spark.stop()


def expire_old_snapshots(**context):
    """Remove snapshots older than 7 days."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    tables = ["fraud_db.transactions", "fraud_db.fraud_alerts", "fraud_db.enriched_transactions"]

    for table in tables:
        try:
            spark.sql(f"""
                CALL nessie.system.expire_snapshots(
                    table => '{table}',
                    older_than => TIMESTAMP '{(datetime.utcnow() - timedelta(days=7)).isoformat()}'
                )
            """)
        except Exception as e:
            print(f"Snapshot expiry failed for {table}: {e}")

    spark.stop()


def vacuum_orphan_files(**context):
    """Remove orphan files not referenced by any Iceberg snapshot."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    tables = ["fraud_db.transactions", "fraud_db.fraud_alerts"]

    for table in tables:
        try:
            spark.sql(f"""
                CALL nessie.system.remove_orphan_files(
                    table => '{table}',
                    older_than => TIMESTAMP '{(datetime.utcnow() - timedelta(days=3)).isoformat()}'
                )
            """)
        except Exception as e:
            print(f"Orphan cleanup failed for {table}: {e}")

    spark.stop()


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="iceberg_maintenance",
    default_args=default_args,
    description="Daily Iceberg table maintenance — compaction, snapshot expiry, orphan cleanup",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["iceberg", "maintenance"],
) as dag:

    compact = PythonOperator(task_id="compact_small_files", python_callable=compact_small_files)
    expire = PythonOperator(task_id="expire_old_snapshots", python_callable=expire_old_snapshots)
    vacuum = PythonOperator(task_id="vacuum_orphan_files", python_callable=vacuum_orphan_files)

    compact >> expire >> vacuum
