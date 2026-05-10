"""Train Isolation Forest anomaly detection model for fraud detection."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import structlog
import yaml
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ml.features.feature_definitions import NUMERIC_FEATURES, ALL_FEATURE_NAMES
from ml.training.data_loader import load_from_csv, load_synthetic, prepare_splits
from ml.training.evaluation import compute_metrics, generate_evaluation_report

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "ml" / "config.yml"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"


def load_config() -> dict:
    """Load training configuration."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def train_isolation_forest(
    data_path: str | None = None,
    version: str | None = None,
) -> dict:
    """Train an Isolation Forest model for anomaly-based fraud detection.

    Args:
        data_path: Path to CSV training data. If None, uses synthetic data.
        version: Model version string. Defaults to timestamp.

    Returns:
        Dictionary with model path and evaluation metrics.
    """
    config = load_config()
    model_config = config["models"]["isolation_forest"]
    training_config = config["training"]

    version = version or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("training_start", model="isolation_forest", version=version)

    # Load data
    if data_path:
        df = load_from_csv(data_path)
    else:
        df = load_synthetic(n_samples=50000, fraud_ratio=0.02)

    # Split data
    splits = prepare_splits(
        df,
        test_size=training_config["test_size"],
        val_size=training_config["val_size"],
        random_state=training_config["random_state"],
    )

    X_train = splits["X_train"]
    X_test = splits["X_test"]
    y_test = splits["y_test"]

    # Scale features (Isolation Forest benefits from scaling)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train[NUMERIC_FEATURES])
    X_test_scaled = scaler.transform(X_test[NUMERIC_FEATURES])

    # Train model
    model = IsolationForest(
        n_estimators=model_config["n_estimators"],
        contamination=model_config["contamination"],
        random_state=model_config["random_state"],
        max_samples=model_config.get("max_samples", "auto"),
        max_features=model_config.get("max_features", 1.0),
        n_jobs=-1,
    )

    logger.info("fitting_model", n_estimators=model_config["n_estimators"])
    model.fit(X_train_scaled)

    # Predict anomaly scores (lower = more anomalous)
    raw_scores = model.decision_function(X_test_scaled)

    # Convert to probability-like score (0 = normal, 1 = fraud)
    # Isolation Forest: more negative = more anomalous
    min_score = raw_scores.min()
    max_score = raw_scores.max()
    score_range = max_score - min_score
    if score_range > 0:
        y_prob = 1.0 - (raw_scores - min_score) / score_range
    else:
        y_prob = np.zeros_like(raw_scores)

    # Evaluate
    report = generate_evaluation_report(
        y_true=y_test.values,
        y_prob=y_prob,
        model_name=f"isolation_forest_v{version}",
        threshold=0.5,
        output_dir=MODELS_DIR,
    )

    # Save model and scaler
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"isolation_forest_v{version}.joblib"
    scaler_path = MODELS_DIR / f"isolation_forest_scaler_v{version}.joblib"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    # Save score normalization params
    norm_params = {
        "min_score": float(min_score),
        "max_score": float(max_score),
        "feature_names": NUMERIC_FEATURES,
    }
    norm_path = MODELS_DIR / f"isolation_forest_norm_v{version}.json"
    with open(norm_path, "w") as f:
        json.dump(norm_params, f, indent=2)

    logger.info(
        "training_complete",
        model="isolation_forest",
        version=version,
        model_path=str(model_path),
        auc_roc=report["metrics"]["auc_roc"],
        auc_pr=report["metrics"]["auc_pr"],
    )

    return {
        "model_path": str(model_path),
        "scaler_path": str(scaler_path),
        "norm_path": str(norm_path),
        "version": version,
        "metrics": report["metrics"],
        "report": report,
    }


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    result = train_isolation_forest(data_path=data_path)
    print(json.dumps(result["metrics"], indent=2))
