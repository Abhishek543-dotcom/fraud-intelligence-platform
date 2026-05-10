"""Train Random Forest classifier for fraud detection."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import structlog
import yaml
from sklearn.ensemble import RandomForestClassifier

from ml.features.feature_definitions import ALL_FEATURE_NAMES
from ml.training.data_loader import load_from_csv, load_synthetic, prepare_splits
from ml.training.evaluation import generate_evaluation_report

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "ml" / "config.yml"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def train_random_forest(
    data_path: str | None = None,
    version: str | None = None,
) -> dict:
    """Train Random Forest classifier for fraud detection.

    Args:
        data_path: Path to CSV training data. If None, uses synthetic data.
        version: Model version string.

    Returns:
        Dictionary with model path and evaluation metrics.
    """
    config = load_config()
    model_config = config["models"]["random_forest"]
    training_config = config["training"]

    version = version or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("training_start", model="random_forest", version=version)

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
        use_smote=training_config.get("use_smote", False),
        smote_ratio=training_config.get("smote_ratio", 0.3),
    )

    X_train = splits["X_train"]
    X_test = splits["X_test"]
    y_train = splits["y_train"]
    y_test = splits["y_test"]

    # Train (no feature scaling needed for tree-based models)
    model = RandomForestClassifier(
        n_estimators=model_config["n_estimators"],
        class_weight=model_config.get("class_weight", "balanced"),
        max_depth=model_config.get("max_depth", 12),
        min_samples_split=model_config.get("min_samples_split", 10),
        n_jobs=model_config.get("n_jobs", -1),
        random_state=model_config.get("random_state", 42),
    )

    logger.info("fitting_model", n_estimators=model_config["n_estimators"])
    model.fit(X_train, y_train)

    # Predict
    y_prob = model.predict_proba(X_test)[:, 1]

    # Evaluate
    report = generate_evaluation_report(
        y_true=y_test.values,
        y_prob=y_prob,
        model_name=f"random_forest_v{version}",
        threshold=0.5,
        output_dir=MODELS_DIR,
    )

    # Feature importance
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    importance = dict(zip(X_train.columns, model.feature_importances_))
    importance_sorted = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
    importance_path = MODELS_DIR / f"random_forest_feature_importance_v{version}.json"
    with open(importance_path, "w") as f:
        json.dump(importance_sorted, f, indent=2)

    # Save model
    model_path = MODELS_DIR / f"random_forest_v{version}.joblib"
    joblib.dump(model, model_path)

    logger.info(
        "training_complete",
        model="random_forest",
        version=version,
        model_path=str(model_path),
        auc_roc=report["metrics"]["auc_roc"],
        auc_pr=report["metrics"]["auc_pr"],
        f1=report["metrics"]["f1"],
    )

    return {
        "model_path": str(model_path),
        "version": version,
        "metrics": report["metrics"],
        "feature_importance": importance_sorted,
        "report": report,
    }


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    result = train_random_forest(data_path=data_path)
    print(json.dumps(result["metrics"], indent=2))
