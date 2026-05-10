"""Main fraud pipeline orchestration DAG."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator


def check_kafka_health(**context):
    """Verify Kafka broker and topics are accessible."""
    from kafka import KafkaAdminClient
    import os

    bootstrap = os.getenv("KAFKA_BROKER", "kafka:9092")
    admin = KafkaAdminClient(bootstrap_servers=bootstrap)
    topics = admin.list_topics()
    required = ["transactions_raw", "transactions_enriched", "fraud_alerts"]
    missing = [t for t in required if t not in topics]
    if missing:
        raise RuntimeError(f"Missing Kafka topics: {missing}")
    admin.close()


def validate_output(**context):
    """Validate that Spark streaming produced output in the expected timeframe."""
    from pyspark.sql import SparkSession
    import os

    spark = SparkSession.builder \
        .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0") \
        .getOrCreate()

    nessie_uri = os.getenv("NESSIE_URI", "http://nessie:19120/api/v1")
    count = spark.sql("""
        SELECT COUNT(*) as cnt FROM nessie.fraud_db.transactions
        WHERE timestamp >= current_timestamp() - INTERVAL 6 HOURS
    """).collect()[0]["cnt"]

    if count == 0:
        raise RuntimeError("No transactions processed in the last 6 hours")

    spark.stop()


def update_metrics(**context):
    """Push pipeline health metrics to Prometheus pushgateway."""
    import requests

    metrics = [
        "fraud_pipeline_last_success_timestamp {}".format(datetime.utcnow().timestamp()),
        "fraud_pipeline_runs_total 1",
    ]
    payload = "\n".join(metrics) + "\n"

    try:
        requests.post(
            "http://prometheus:9091/metrics/job/fraud_pipeline",
            data=payload,
            timeout=10,
        )
    except Exception:
        pass  # Non-critical


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="fraud_pipeline_orchestration",
    default_args=default_args,
    description="Main fraud detection pipeline orchestration — runs every 6 hours",
    schedule_interval="0 */6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["fraud", "pipeline", "orchestration"],
) as dag:

    check_kafka = PythonOperator(
        task_id="check_kafka_health",
        python_callable=check_kafka_health,
    )

    run_streaming = BashOperator(
        task_id="run_spark_streaming",
        bash_command=(
            "spark-submit --master spark://spark-master:7077 "
            "--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0 "
            "/opt/spark-jobs/streaming_pipeline.py "
            "--duration 300"
        ),
    )

    validate = PythonOperator(
        task_id="validate_output",
        python_callable=validate_output,
    )

    metrics = PythonOperator(
        task_id="update_metrics",
        python_callable=update_metrics,
    )

    check_kafka >> run_streaming >> validate >> metrics
