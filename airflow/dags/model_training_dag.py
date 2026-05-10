"""ML model training DAG — weekly retraining pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def extract_training_data(**context):
    """Extract labeled training data from Iceberg tables."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    df = spark.sql("""
        SELECT * FROM nessie.fraud_db.transactions
        WHERE timestamp >= current_date() - INTERVAL 30 DAYS
    """)

    output_path = "s3://lakehouse/training_data/latest/"
    df.write.mode("overwrite").parquet(output_path)
    context["ti"].xcom_push(key="training_data_path", value=output_path)
    context["ti"].xcom_push(key="sample_count", value=df.count())
    spark.stop()


def train_models(**context):
    """Train XGBoost and isolation forest models."""
    import joblib
    import pandas as pd
    from sklearn.ensemble import IsolationForest
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    data_path = context["ti"].xcom_pull(key="training_data_path")
    df = pd.read_parquet(data_path.replace("s3://", "/data/"))

    feature_cols = [
        "amount", "customer_lat", "customer_lon", "is_international",
        "card_present",
    ]
    X = df[feature_cols].fillna(0)
    y = df["is_fraud"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    xgb = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1, scale_pos_weight=50, random_state=42)
    xgb.fit(X_train, y_train)
    xgb_accuracy = xgb.score(X_test, y_test)

    iso = IsolationForest(n_estimators=100, contamination=0.02, random_state=42)
    iso.fit(X_train)

    model_dir = "/tmp/models/"
    import os
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(xgb, f"{model_dir}/xgboost_fraud.pkl")
    joblib.dump(iso, f"{model_dir}/isolation_forest.pkl")

    context["ti"].xcom_push(key="xgb_accuracy", value=round(xgb_accuracy, 4))
    context["ti"].xcom_push(key="model_dir", value=model_dir)


def evaluate_models(**context):
    """Evaluate trained models against the holdout set."""
    accuracy = context["ti"].xcom_pull(key="xgb_accuracy")
    if accuracy < 0.85:
        raise ValueError(f"Model accuracy {accuracy} below threshold 0.85, not promoting.")


def promote_best(**context):
    """Promote the best model to the production model registry."""
    import shutil
    model_dir = context["ti"].xcom_pull(key="model_dir")
    prod_dir = "/models/production/"
    import os
    os.makedirs(prod_dir, exist_ok=True)
    for f in os.listdir(model_dir):
        shutil.copy2(os.path.join(model_dir, f), os.path.join(prod_dir, f))


def deploy_model(**context):
    """Notify the ML service to reload models."""
    import requests
    try:
        requests.post("http://ml-service:8001/reload", timeout=30)
    except Exception:
        pass


default_args = {
    "owner": "fraud-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="model_training_pipeline",
    default_args=default_args,
    description="Weekly ML model retraining pipeline",
    schedule_interval="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "training", "fraud"],
) as dag:

    extract = PythonOperator(task_id="extract_training_data", python_callable=extract_training_data)
    train = PythonOperator(task_id="train_models", python_callable=train_models)
    evaluate = PythonOperator(task_id="evaluate_models", python_callable=evaluate_models)
    promote = PythonOperator(task_id="promote_best", python_callable=promote_best)
    deploy = PythonOperator(task_id="deploy_model", python_callable=deploy_model)

    extract >> train >> evaluate >> promote >> deploy
