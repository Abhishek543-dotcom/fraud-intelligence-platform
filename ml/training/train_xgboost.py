"""Train XGBoost classifier for fraud detection."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import structlog
import yaml
from xgboost import XGBClassifier

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


def _optuna_tune(X_train, y_train, X_val, y_val, n_trials: int = 50) -> dict[str, Any]:
    """Run Optuna hyperparameter optimization."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 10, 100),
        }

        model = XGBClassifier(
            **params,
            tree_method="hist",
            eval_metric="aucpr",
            random_state=42,
            verbosity=0,
        )

        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        y_prob = model.predict_proba(X_val)[:, 1]
        from sklearn.metrics import average_precision_score

        return average_precision_score(y_val, y_prob)

    study = optuna.create_study(direction="maximize", study_name="xgboost_fraud")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    logger.info(
        "optuna_complete",
        best_value=study.best_value,
        best_params=study.best_params,
        n_trials=n_trials,
    )
    return study.best_params


def train_xgboost(
    data_path: str | None = None,
    version: str | None = None,
    enable_optuna: bool | None = None,
) -> dict:
    """Train XGBoost classifier for fraud detection.

    Args:
        data_path: Path to CSV training data. If None, uses synthetic data.
        version: Model version string.
        enable_optuna: Whether to run hyperparameter tuning. Overrides config if set.

    Returns:
        Dictionary with model path and evaluation metrics.
    """
    config = load_config()
    model_config = config["models"]["xgboost"]
    training_config = config["training"]

    version = version or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("training_start", model="xgboost", version=version)

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
    X_val = splits["X_val"]
    X_test = splits["X_test"]
    y_train = splits["y_train"]
    y_val = splits["y_val"]
    y_test = splits["y_test"]

    # Optuna tuning
    use_optuna = enable_optuna if enable_optuna is not None else training_config.get("enable_optuna", False)
    if use_optuna:
        logger.info("running_optuna", n_trials=training_config.get("optuna_trials", 50))
        best_params = _optuna_tune(
            X_train, y_train, X_val, y_val, n_trials=training_config.get("optuna_trials", 50)
        )
        xgb_params = best_params
    else:
        xgb_params = {
            "n_estimators": model_config["n_estimators"],
            "max_depth": model_config["max_depth"],
            "learning_rate": model_config["learning_rate"],
            "scale_pos_weight": model_config["scale_pos_weight"],
        }

    # Train
    model = XGBClassifier(
        **xgb_params,
        tree_method=model_config.get("tree_method", "hist"),
        eval_metric=model_config.get("eval_metric", "aucpr"),
        early_stopping_rounds=model_config.get("early_stopping_rounds", 20),
        random_state=model_config.get("random_state", 42),
        verbosity=0,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Predict
    y_prob = model.predict_proba(X_test)[:, 1]

    # Evaluate
    report = generate_evaluation_report(
        y_true=y_test.values,
        y_prob=y_prob,
        model_name=f"xgboost_v{version}",
        threshold=0.5,
        output_dir=MODELS_DIR,
    )

    # Feature importance
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    importance = dict(zip(X_train.columns, model.feature_importances_))
    importance_sorted = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
    importance_path = MODELS_DIR / f"xgboost_feature_importance_v{version}.json"
    with open(importance_path, "w") as f:
        json.dump(importance_sorted, f, indent=2)

    # Save feature importance plot
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))
        features = list(importance_sorted.keys())[:15]
        values = [importance_sorted[f] for f in features]
        ax.barh(features[::-1], values[::-1])
        ax.set_xlabel("Feature Importance")
        ax.set_title(f"XGBoost Feature Importance (v{version})")
        plt.tight_layout()
        plot_path = MODELS_DIR / f"xgboost_importance_v{version}.png"
        fig.savefig(plot_path, dpi=100)
        plt.close(fig)
        logger.info("importance_plot_saved", path=str(plot_path))
    except Exception as e:
        logger.warning("importance_plot_failed", error=str(e))

    # Save model
    model_path = MODELS_DIR / f"xgboost_v{version}.json"
    model.save_model(str(model_path))

    logger.info(
        "training_complete",
        model="xgboost",
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
        "params": xgb_params,
    }


if __name__ == "__main__":
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    result = train_xgboost(data_path=data_path)
    print(json.dumps(result["metrics"], indent=2))
