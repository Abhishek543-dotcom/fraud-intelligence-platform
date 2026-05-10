"""Data quality validation DAG using Great Expectations."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def run_transaction_validation(**context):
    """Validate transaction data quality."""
    import great_expectations as gx

    ge_context = gx.get_context(context_root_dir="/opt/airflow/data-quality")
    result = ge_context.run_checkpoint(
        checkpoint_name="transactions_checkpoint",
        expectation_suite_name="transactions_suite",
    )
    if not result.success:
        failed = [r.expectation_config.expectation_type for r in result.results if not r.success]
        raise ValueError(f"Transaction validation failed: {failed}")


def run_alert_validation(**context):
    """Validate fraud alert data quality."""
    import great_expectations as gx

    ge_context = gx.get_context(context_root_dir="/opt/airflow/data-quality")
    result = ge_context.run_checkpoint(
        checkpoint_name="fraud_alerts_checkpoint",
        expectation_suite_name="fraud_alerts_suite",
    )
    if not result.success:
        failed = [r.expectation_config.expectation_type for r in result.results if not r.success]
        raise ValueError(f"Alert validation failed: {failed}")


def publish_quality_metrics(**context):
    """Publish data quality results to Prometheus."""
    import requests

    metrics = "data_quality_last_success_timestamp {}\n".format(datetime.utcnow().timestamp())
    try:
        requests.post("http://prometheus:9091/metrics/job/data_quality", data=metrics, timeout=10)
    except Exception:
        pass


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="data_quality_validation",
    default_args=default_args,
    description="Daily data quality validation with Great Expectations",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["data-quality", "validation"],
) as dag:

    validate_txns = PythonOperator(task_id="validate_transactions", python_callable=run_transaction_validation)
    validate_alerts = PythonOperator(task_id="validate_fraud_alerts", python_callable=run_alert_validation)
    publish = PythonOperator(task_id="publish_quality_metrics", python_callable=publish_quality_metrics)

    [validate_txns, validate_alerts] >> publish
