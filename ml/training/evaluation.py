"""Comprehensive model evaluation for fraud detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sklearn.metrics import (
    accuracy_score,
    auc,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

logger = structlog.get_logger(__name__)


def compute_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compute comprehensive classification metrics."""
    y_pred = (y_prob >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc_roc": float(roc_auc_score(y_true, y_prob)),
        "auc_pr": float(average_precision_score(y_true, y_prob)),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "threshold": threshold,
    }

    return metrics


def precision_at_recall(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    target_recall: float = 0.9,
) -> dict[str, float]:
    """Find precision at a target recall level."""
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    # Find the threshold that gives us at least target_recall
    valid = recalls >= target_recall
    if not valid.any():
        return {"precision_at_recall": 0.0, "threshold": 1.0, "target_recall": target_recall}

    idx = np.argmax(precisions[valid])
    return {
        "precision_at_recall": float(precisions[valid][idx]),
        "threshold": float(thresholds[np.where(valid)[0][idx]]) if idx < len(thresholds) else 0.0,
        "target_recall": target_recall,
    }


def cost_sensitive_evaluation(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.5,
    fn_cost: float = 10.0,
    fp_cost: float = 1.0,
) -> dict[str, float]:
    """Cost-sensitive evaluation weighting false negatives more heavily.

    In fraud detection, missing a fraud (FN) is far more costly than
    flagging a legitimate transaction (FP).
    """
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    total_cost = fn * fn_cost + fp * fp_cost
    max_possible_cost = (fn + tp) * fn_cost  # if we missed all fraud
    normalized_cost = total_cost / max_possible_cost if max_possible_cost > 0 else 0.0

    return {
        "total_cost": float(total_cost),
        "fn_cost_contribution": float(fn * fn_cost),
        "fp_cost_contribution": float(fp * fp_cost),
        "normalized_cost": float(normalized_cost),
        "cost_savings_vs_no_model": float(max_possible_cost - total_cost),
        "fn_cost_weight": fn_cost,
        "fp_cost_weight": fp_cost,
    }


def find_optimal_threshold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    metric: str = "f1",
) -> dict[str, float]:
    """Find the threshold that maximizes the given metric."""
    thresholds = np.arange(0.01, 1.0, 0.01)
    best_score = -1.0
    best_threshold = 0.5

    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        if metric == "f1":
            score = f1_score(y_true, y_pred, zero_division=0)
        elif metric == "precision":
            score = precision_score(y_true, y_pred, zero_division=0)
        elif metric == "recall":
            score = recall_score(y_true, y_pred, zero_division=0)
        else:
            score = f1_score(y_true, y_pred, zero_division=0)

        if score > best_score:
            best_score = score
            best_threshold = t

    return {
        "optimal_threshold": float(best_threshold),
        "best_score": float(best_score),
        "metric": metric,
    }


def generate_evaluation_report(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    model_name: str,
    threshold: float = 0.5,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive evaluation report for a model."""
    report: dict[str, Any] = {
        "model_name": model_name,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_size": len(y_true),
        "positive_samples": int(y_true.sum()),
        "negative_samples": int(len(y_true) - y_true.sum()),
    }

    # Standard metrics
    report["metrics"] = compute_metrics(y_true, y_prob, threshold)

    # Precision at common recall targets
    report["precision_at_recall"] = {}
    for recall_target in [0.8, 0.9, 0.95]:
        key = f"recall_{int(recall_target * 100)}"
        report["precision_at_recall"][key] = precision_at_recall(y_true, y_prob, recall_target)

    # Cost-sensitive evaluation
    report["cost_analysis"] = cost_sensitive_evaluation(y_true, y_prob, threshold)

    # Optimal threshold
    report["optimal_threshold"] = find_optimal_threshold(y_true, y_prob, metric="f1")

    # Classification report
    y_pred = (y_prob >= threshold).astype(int)
    report["classification_report"] = classification_report(y_true, y_pred, output_dict=True)

    # Score distribution
    fraud_scores = y_prob[y_true == 1]
    legit_scores = y_prob[y_true == 0]
    report["score_distribution"] = {
        "fraud_mean": float(fraud_scores.mean()) if len(fraud_scores) > 0 else 0.0,
        "fraud_std": float(fraud_scores.std()) if len(fraud_scores) > 0 else 0.0,
        "legit_mean": float(legit_scores.mean()) if len(legit_scores) > 0 else 0.0,
        "legit_std": float(legit_scores.std()) if len(legit_scores) > 0 else 0.0,
    }

    # Save report
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{model_name}_evaluation.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("evaluation_report_saved", path=str(report_path))

    logger.info(
        "evaluation_complete",
        model=model_name,
        auc_roc=report["metrics"]["auc_roc"],
        auc_pr=report["metrics"]["auc_pr"],
        f1=report["metrics"]["f1"],
        precision=report["metrics"]["precision"],
        recall=report["metrics"]["recall"],
    )

    return report


def compare_models(reports: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a comparison table from multiple evaluation reports."""
    rows = []
    for r in reports:
        m = r.get("metrics", {})
        opt = r.get("optimal_threshold", {})
        cost = r.get("cost_analysis", {})
        rows.append(
            {
                "model": r.get("model_name", "unknown"),
                "auc_roc": m.get("auc_roc", 0.0),
                "auc_pr": m.get("auc_pr", 0.0),
                "f1": m.get("f1", 0.0),
                "precision": m.get("precision", 0.0),
                "recall": m.get("recall", 0.0),
                "optimal_threshold": opt.get("optimal_threshold", 0.5),
                "best_f1": opt.get("best_score", 0.0),
                "normalized_cost": cost.get("normalized_cost", 0.0),
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("auc_pr", ascending=False).reset_index(drop=True)
    return df
