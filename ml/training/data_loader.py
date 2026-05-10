"""Data loader for fraud detection model training."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sklearn.model_selection import train_test_split

from ml.features.feature_definitions import ALL_FEATURE_NAMES
from ml.features.feature_pipeline import generate_synthetic_features

logger = structlog.get_logger(__name__)

TARGET_COLUMN = "is_fraud"


def load_from_csv(path: str | Path) -> pd.DataFrame:
    """Load training data from a CSV file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Training data not found: {path}")

    df = pd.read_csv(path)
    logger.info("csv_data_loaded", path=str(path), rows=len(df), columns=list(df.columns))
    return df


def load_from_iceberg(
    table_name: str = "nessie.fraud_db.silver_transactions",
    spark_master: str = "spark://spark-master:7077",
) -> pd.DataFrame:
    """Load training data from Iceberg silver table via PySpark."""
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        logger.error("pyspark_not_available", hint="Install pyspark to load from Iceberg")
        raise

    spark = (
        SparkSession.builder.appName("FraudML-DataLoader")
        .master(spark_master)
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
        .getOrCreate()
    )

    try:
        spark_df = spark.sql(f"SELECT * FROM {table_name}")
        df = spark_df.toPandas()
        logger.info("iceberg_data_loaded", table=table_name, rows=len(df))
        return df
    finally:
        spark.stop()


def load_synthetic(n_samples: int = 50000, fraud_ratio: float = 0.02) -> pd.DataFrame:
    """Generate synthetic training data for development."""
    df = generate_synthetic_features(n_samples=n_samples, fraud_ratio=fraud_ratio)
    logger.info("synthetic_data_loaded", rows=len(df), fraud_ratio=fraud_ratio)
    return df


def prepare_splits(
    df: pd.DataFrame,
    test_size: float = 0.15,
    val_size: float = 0.15,
    random_state: int = 42,
    use_smote: bool = False,
    smote_ratio: float = 0.3,
) -> dict[str, Any]:
    """Split data into train/val/test sets with optional SMOTE oversampling.

    Returns a dict with keys: X_train, X_val, X_test, y_train, y_val, y_test, stats.
    """
    feature_cols = [c for c in ALL_FEATURE_NAMES if c in df.columns]
    X = df[feature_cols].copy()
    y = df[TARGET_COLUMN].copy()

    # Class distribution
    class_counts = y.value_counts().to_dict()
    fraud_pct = class_counts.get(1, 0) / len(y) * 100
    logger.info("class_distribution", counts=class_counts, fraud_pct=f"{fraud_pct:.2f}%")

    # Split: first carve test, then split remainder into train/val
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    relative_val_size = val_size / (1 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=relative_val_size, random_state=random_state, stratify=y_temp
    )

    logger.info(
        "data_split",
        train=len(X_train),
        val=len(X_val),
        test=len(X_test),
        train_fraud_pct=f"{y_train.mean() * 100:.2f}%",
    )

    # SMOTE oversampling on training set only
    if use_smote:
        try:
            from imblearn.over_sampling import SMOTE

            smote = SMOTE(sampling_strategy=smote_ratio, random_state=random_state)
            X_train, y_train = smote.fit_resample(X_train, y_train)
            logger.info(
                "smote_applied",
                new_train_size=len(X_train),
                new_fraud_pct=f"{y_train.mean() * 100:.2f}%",
            )
        except ImportError:
            logger.warning("smote_unavailable", hint="Install imbalanced-learn for SMOTE")

    stats = {
        "total_samples": len(df),
        "train_samples": len(X_train),
        "val_samples": len(X_val),
        "test_samples": len(X_test),
        "feature_count": len(feature_cols),
        "fraud_ratio": fraud_pct,
        "smote_applied": use_smote,
    }

    return {
        "X_train": X_train.reset_index(drop=True),
        "X_val": X_val.reset_index(drop=True),
        "X_test": X_test.reset_index(drop=True),
        "y_train": y_train.reset_index(drop=True),
        "y_val": y_val.reset_index(drop=True),
        "y_test": y_test.reset_index(drop=True),
        "stats": stats,
    }
