"""Airflow DAG for Great Expectations data quality validation."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def validate_transactions(**context):
    """Run Great Expectations validation on the transactions Iceberg table."""
    import great_expectations as gx

    ge_context = gx.get_context(
        context_root_dir="/opt/airflow/data-quality"
    )

    checkpoint_result = ge_context.run_checkpoint(
        checkpoint_name="transactions_checkpoint",
        batch_request={
            "datasource_name": "iceberg_datasource",
            "data_asset_name": "fraud_db.transactions",
        },
        expectation_suite_name="transactions_suite",
    )

    if not checkpoint_result.success:
        failed = [
            r.expectation_config.expectation_type
            for r in checkpoint_result.results
            if not r.success
        ]
        raise ValueError(f"Transaction data quality check failed: {failed}")


def validate_fraud_alerts(**context):
    """Run Great Expectations validation on the fraud alerts Iceberg table."""
    import great_expectations as gx

    ge_context = gx.get_context(
        context_root_dir="/opt/airflow/data-quality"
    )

    checkpoint_result = ge_context.run_checkpoint(
        checkpoint_name="fraud_alerts_checkpoint",
        batch_request={
            "datasource_name": "iceberg_datasource",
            "data_asset_name": "fraud_db.fraud_alerts",
        },
        expectation_suite_name="fraud_alerts_suite",
    )

    if not checkpoint_result.success:
        failed = [
            r.expectation_config.expectation_type
            for r in checkpoint_result.results
            if not r.success
        ]
        raise ValueError(f"Fraud alerts data quality check failed: {failed}")


def generate_data_docs(**context):
    """Build Great Expectations data documentation site."""
    import great_expectations as gx

    ge_context = gx.get_context(
        context_root_dir="/opt/airflow/data-quality"
    )
    ge_context.build_data_docs()


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="data_quality_validation",
    default_args=default_args,
    description="Daily Great Expectations data quality validation on Iceberg tables",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["data-quality", "great-expectations"],
) as dag:

    validate_txns = PythonOperator(
        task_id="validate_transactions",
        python_callable=validate_transactions,
    )

    validate_alerts = PythonOperator(
        task_id="validate_fraud_alerts",
        python_callable=validate_fraud_alerts,
    )

    build_docs = PythonOperator(
        task_id="generate_data_docs",
        python_callable=generate_data_docs,
    )

    [validate_txns, validate_alerts] >> build_docs
