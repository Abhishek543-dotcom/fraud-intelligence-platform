"""Feature store refresh DAG — materializes online and offline features."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def refresh_customer_features(**context):
    """Compute and refresh customer-level features in Redis."""
    from pyspark.sql import SparkSession
    import redis
    import json

    spark = SparkSession.builder.getOrCreate()

    df = spark.sql("""
        SELECT
            customer_id,
            COUNT(*) as txn_count_30d,
            AVG(amount) as avg_amount_30d,
            MAX(amount) as max_amount_30d,
            SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) as fraud_count_30d,
            COUNT(DISTINCT merchant_id) as unique_merchants_30d,
            COUNT(DISTINCT merchant_country) as unique_countries_30d
        FROM nessie.fraud_db.transactions
        WHERE timestamp >= current_date() - INTERVAL 30 DAYS
        GROUP BY customer_id
    """)

    r = redis.from_url("redis://redis:6379/0")
    rows = df.collect()
    pipe = r.pipeline()

    for row in rows:
        key = f"features:customer:{row['customer_id']}"
        features = {
            "txn_count_30d": row["txn_count_30d"],
            "avg_amount_30d": float(row["avg_amount_30d"] or 0),
            "max_amount_30d": float(row["max_amount_30d"] or 0),
            "fraud_count_30d": row["fraud_count_30d"],
            "unique_merchants_30d": row["unique_merchants_30d"],
            "unique_countries_30d": row["unique_countries_30d"],
        }
        pipe.hset(key, mapping={k: json.dumps(v) for k, v in features.items()})
        pipe.expire(key, 86400)

    pipe.execute()
    spark.stop()
    context["ti"].xcom_push(key="customers_refreshed", value=len(rows))


def refresh_merchant_features(**context):
    """Compute and refresh merchant-level features in Redis."""
    from pyspark.sql import SparkSession
    import redis
    import json

    spark = SparkSession.builder.getOrCreate()

    df = spark.sql("""
        SELECT
            merchant_id,
            COUNT(*) as txn_count_30d,
            AVG(amount) as avg_amount_30d,
            SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) as fraud_count_30d,
            SUM(CASE WHEN is_fraud THEN 1.0 ELSE 0.0 END) / COUNT(*) as fraud_rate_30d,
            COUNT(DISTINCT customer_id) as unique_customers_30d
        FROM nessie.fraud_db.transactions
        WHERE timestamp >= current_date() - INTERVAL 30 DAYS
        GROUP BY merchant_id
    """)

    r = redis.from_url("redis://redis:6379/0")
    rows = df.collect()
    pipe = r.pipeline()

    for row in rows:
        key = f"features:merchant:{row['merchant_id']}"
        features = {
            "txn_count_30d": row["txn_count_30d"],
            "avg_amount_30d": float(row["avg_amount_30d"] or 0),
            "fraud_count_30d": row["fraud_count_30d"],
            "fraud_rate_30d": float(row["fraud_rate_30d"] or 0),
            "unique_customers_30d": row["unique_customers_30d"],
        }
        pipe.hset(key, mapping={k: json.dumps(v) for k, v in features.items()})
        pipe.expire(key, 86400)

    pipe.execute()
    spark.stop()
    context["ti"].xcom_push(key="merchants_refreshed", value=len(rows))


def materialize_offline_features(**context):
    """Write aggregated features to Iceberg for offline training."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    spark.sql("""
        INSERT OVERWRITE nessie.fraud_db.features_customer
        SELECT
            customer_id,
            current_timestamp() as computed_at,
            COUNT(*) as txn_count_30d,
            AVG(amount) as avg_amount_30d,
            STDDEV(amount) as std_amount_30d,
            MAX(amount) as max_amount_30d,
            MIN(amount) as min_amount_30d,
            SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) as fraud_count_30d,
            COUNT(DISTINCT merchant_id) as unique_merchants_30d,
            COUNT(DISTINCT merchant_country) as unique_countries_30d,
            COUNT(DISTINCT device_id) as unique_devices_30d
        FROM nessie.fraud_db.transactions
        WHERE timestamp >= current_date() - INTERVAL 30 DAYS
        GROUP BY customer_id
    """)

    spark.stop()


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="feature_store_refresh",
    default_args=default_args,
    description="Daily feature store refresh — online (Redis) and offline (Iceberg)",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["features", "ml", "redis"],
) as dag:

    customer_features = PythonOperator(
        task_id="refresh_customer_features",
        python_callable=refresh_customer_features,
    )

    merchant_features = PythonOperator(
        task_id="refresh_merchant_features",
        python_callable=refresh_merchant_features,
    )

    offline = PythonOperator(
        task_id="materialize_offline_features",
        python_callable=materialize_offline_features,
    )

    [customer_features, merchant_features] >> offline
