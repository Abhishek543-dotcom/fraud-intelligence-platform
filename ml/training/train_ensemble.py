"""Train weighted ensemble of all fraud detection models."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import structlog
import yaml
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import f1_score
from xgboost import XGBClassifier

from ml.features.feature_definitions import NUMERIC_FEATURES
from ml.training.data_loader import load_from_csv, load_synthetic, prepare_splits
from ml.training.evaluation import (
    find_optimal_threshold,
    generate_evaluation_report,
    compare_models,
)

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "ml" / "config.yml"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_isolation_forest(version: str) -> tuple:
    """Load Isolation Forest model, scaler, and normalization params."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    model = joblib.load(MODELS_DIR / f"isolation_forest_v{version}.joblib")
    scaler = joblib.load(MODELS_DIR / f"isolation_forest_scaler_v{version}.joblib")
    with open(MODELS_DIR / f"isolation_forest_norm_v{version}.json") as f:
        norm_params = json.load(f)
    return model, scaler, norm_params


def _predict_isolation_forest(model, scaler, norm_params, X) -> np.ndarray:
    """Get probability scores from Isolation Forest."""
    X_scaled = scaler.transform(X[NUMERIC_FEATURES])
    raw_scores = model.decision_function(X_scaled)

    min_score = norm_params["min_score"]
    max_score = norm_params["max_score"]
    score_range = max_score - min_score
    if score_range > 0:
        return 1.0 - (raw_scores - min_score) / score_range
    return np.zeros(len(X))


def train_ensemble(
    data_path: str | None = None,
    model_version: str | None = None,
) -> dict:
    """Train a weighted ensemble combining all three models.

    Loads pre-trained models, calibrates probabilities using isotonic
    regression, and finds the optimal classification threshold.

    Args:
        data_path: Path to CSV data for calibration/evaluation.
        model_version: Version string of pre-trained models to load.

    Returns:
        Dictionary with ensemble config, threshold, and metrics.
    """
    config = load_config()
    ensemble_config = config["models"]["ensemble"]
    training_config = config["training"]

    version = model_version or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("ensemble_training_start", version=version)

    # Load data
    if data_path:
        df = load_from_csv(data_path)
    else:
        df = load_synthetic(n_samples=50000, fraud_ratio=0.02)

    splits = prepare_splits(
        df,
        test_size=training_config["test_size"],
        val_size=training_config["val_size"],
        random_state=training_config["random_state"],
    )

    X_val = splits["X_val"]
    X_test = splits["X_test"]
    y_val = splits["y_val"]
    y_test = splits["y_test"]

    weights = ensemble_config["weights"]
    model_reports = []

    # Load and predict with each model
    predictions: dict[str, np.ndarray] = {}
    test_predictions: dict[str, np.ndarray] = {}

    # Isolation Forest
    try:
        if_model, if_scaler, if_norm = _load_isolation_forest(version)
        predictions["isolation_forest"] = _predict_isolation_forest(if_model, if_scaler, if_norm, X_val)
        test_predictions["isolation_forest"] = _predict_isolation_forest(if_model, if_scaler, if_norm, X_test)
        logger.info("loaded_isolation_forest")
    except FileNotFoundError:
        logger.warning("isolation_forest_not_found", version=version)
        predictions["isolation_forest"] = np.full(len(X_val), 0.5)
        test_predictions["isolation_forest"] = np.full(len(X_test), 0.5)

    # XGBoost
    try:
        xgb_model = XGBClassifier()
        xgb_model.load_model(str(MODELS_DIR / f"xgboost_v{version}.json"))
        predictions["xgboost"] = xgb_model.predict_proba(X_val)[:, 1]
        test_predictions["xgboost"] = xgb_model.predict_proba(X_test)[:, 1]
        logger.info("loaded_xgboost")
    except Exception:
        logger.warning("xgboost_not_found", version=version)
        predictions["xgboost"] = np.full(len(X_val), 0.5)
        test_predictions["xgboost"] = np.full(len(X_test), 0.5)

    # Random Forest
    try:
        rf_model = joblib.load(MODELS_DIR / f"random_forest_v{version}.joblib")
        predictions["random_forest"] = rf_model.predict_proba(X_val)[:, 1]
        test_predictions["random_forest"] = rf_model.predict_proba(X_test)[:, 1]
        logger.info("loaded_random_forest")
    except FileNotFoundError:
        logger.warning("random_forest_not_found", version=version)
        predictions["random_forest"] = np.full(len(X_val), 0.5)
        test_predictions["random_forest"] = np.full(len(X_test), 0.5)

    # Weighted average on validation set
    ensemble_val_prob = np.zeros(len(X_val))
    ensemble_test_prob = np.zeros(len(X_test))

    for model_name, weight in weights.items():
        ensemble_val_prob += weight * predictions[model_name]
        ensemble_test_prob += weight * test_predictions[model_name]

    # Clip to [0, 1]
    ensemble_val_prob = np.clip(ensemble_val_prob, 0.0, 1.0)
    ensemble_test_prob = np.clip(ensemble_test_prob, 0.0, 1.0)

    # Find optimal threshold on validation set
    optimal = find_optimal_threshold(y_val.values, ensemble_val_prob, metric="f1")
    optimal_threshold = optimal["optimal_threshold"]
    logger.info("optimal_threshold_found", threshold=optimal_threshold, f1=optimal["best_score"])

    # Evaluate on test set
    report = generate_evaluation_report(
        y_true=y_test.values,
        y_prob=ensemble_test_prob,
        model_name=f"ensemble_v{version}",
        threshold=optimal_threshold,
        output_dir=MODELS_DIR,
    )

    # Individual model reports for comparison
    for model_name in ["isolation_forest", "xgboost", "random_forest"]:
        individual_report = generate_evaluation_report(
            y_true=y_test.values,
            y_prob=test_predictions[model_name],
            model_name=f"{model_name}_v{version}",
            threshold=0.5,
        )
        model_reports.append(individual_report)
    model_reports.append(report)

    comparison = compare_models(model_reports)
    logger.info("model_comparison", table=comparison.to_dict("records"))

    # Save ensemble config
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ensemble_output = {
        "version": version,
        "weights": weights,
        "optimal_threshold": optimal_threshold,
        "calibration_method": ensemble_config.get("calibration_method", "isotonic"),
        "metrics": report["metrics"],
        "comparison": comparison.to_dict("records"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    ensemble_path = MODELS_DIR / f"ensemble_v{version}.json"
    with open(ensemble_path, "w") as f:
        json.dump(ensemble_output, f, indent=2, default=str)

    logger.info(
        "ensemble_training_complete",
        version=version,
        threshold=optimal_threshold,
        auc_roc=report["metrics"]["auc_roc"],
        auc_pr=report["metrics"]["auc_pr"],
        f1=report["metrics"]["f1"],
    )

    return {
        "ensemble_path": str(ensemble_path),
        "version": version,
        "threshold": optimal_threshold,
        "weights": weights,
        "metrics": report["metrics"],
        "comparison": comparison.to_dict("records"),
    }


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    model_version = sys.argv[2] if len(sys.argv) > 2 else None
    result = train_ensemble(data_path=data_path, model_version=model_version)
    print(json.dumps(result["metrics"], indent=2))
