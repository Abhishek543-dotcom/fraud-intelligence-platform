"""ML predictions endpoints — proxies to the real ML service when reachable,
falls back to random mock data otherwise."""

import os
import random
from datetime import datetime

import httpx
import structlog
from fastapi import APIRouter, Query

from app.models.schemas import (
    ModelMetricsResponse,
    APIResponse,
)

logger = structlog.get_logger()
router = APIRouter()

# ---------------------------------------------------------------------------
# ML service configuration
# ---------------------------------------------------------------------------

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://ml-service:8000").rstrip("/")
_HTTP_TIMEOUT = 5.0

MODEL_CONFIGS = [
    ("XGBoost", "2.1.0"),
    ("LightGBM", "1.3.0"),
    ("Ensemble", "3.0.0"),
]

# Static model metadata for comparison (used when ML service is unavailable)
_MODEL_COMPARISON_STATIC = [
    {
        "model_name": "XGBoost",
        "model_version": "2.1.0",
        "model_type": "xgboost",
        "description": "Gradient boosted trees — fast, handles imbalanced data well",
    },
    {
        "model_name": "Random Forest",
        "model_version": "2.1.0",
        "model_type": "random_forest",
        "description": "Bagging ensemble — robust to noise, good interpretability",
    },
    {
        "model_name": "Isolation Forest",
        "model_version": "2.1.0",
        "model_type": "isolation_forest",
        "description": "Unsupervised anomaly detector — finds novel fraud patterns",
    },
    {
        "model_name": "Ensemble",
        "model_version": "3.0.0",
        "model_type": "ensemble",
        "description": "Weighted ensemble of all models — best overall performance",
    },
]


async def _ml_get(path: str) -> dict | None:
    """Make a GET request to the ML service. Returns parsed JSON or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(f"{ML_SERVICE_URL}{path}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("ml_service_unreachable", path=path, error=str(exc))
        return None


async def _ml_post(path: str, payload: dict) -> dict | None:
    """Make a POST request to the ML service. Returns parsed JSON or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(f"{ML_SERVICE_URL}{path}", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("ml_service_post_failed", path=path, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Mock data generators (fallback)
# ---------------------------------------------------------------------------


def _mock_metrics() -> list[dict]:
    metrics = []
    for name, version in MODEL_CONFIGS:
        total_preds = random.randint(30000, 60000)
        precision = round(random.uniform(0.90, 0.96), 4)
        recall = round(random.uniform(0.85, 0.94), 4)
        # Derive confusion matrix from precision/recall
        tp = int(total_preds * 0.02 * recall)  # ~2% actual fraud rate
        fn = int(total_preds * 0.02 * (1 - recall))
        fp = int(tp * (1 - precision) / precision) if precision > 0 else 50
        tn = total_preds - tp - fn - fp
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        metrics.append({
            "model_version": f"{name} v{version}",
            "precision": precision,
            "recall": recall,
            "f1_score": round(f1, 4),
            "auc_roc": round(random.uniform(0.94, 0.99), 4),
            "total_predictions": total_preds,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "avg_latency_ms": round(random.uniform(12, 48), 1),
            "timestamp": datetime.utcnow().isoformat(),
        })
    return metrics


def _mock_predictions(page_size: int) -> list[dict]:
    predictions = []
    for _ in range(min(page_size, 50)):
        model_name, model_version = random.choice(MODEL_CONFIGS)
        fraud_prob = round(random.random(), 4)
        predictions.append({
            "prediction_id": f"PRED-{random.randint(100000, 999999)}",
            "transaction_id": f"TXN-{random.randint(100000, 999999):012X}",
            "model_name": model_name,
            "model_version": model_version,
            "fraud_probability": fraud_prob,
            "is_fraud": fraud_prob > 0.5,
            "features_used": ["amount", "velocity", "geo_distance", "time_delta", "device_score"],
            "inference_time_ms": round(random.uniform(8, 50), 1),
            "timestamp": datetime.utcnow().isoformat(),
        })
    return predictions


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/ml/metrics")
async def model_metrics():
    """Get ML model performance metrics."""

    # Try real ML service first
    info = await _ml_get("/model/info")
    if info is not None:
        ensemble_metrics = info.get("metrics", {})
        if ensemble_metrics:
            # Build per-model metrics from ensemble info
            real_metrics = []
            for model_type in ["xgboost", "random_forest", "isolation_forest", "ensemble"]:
                m = ensemble_metrics.get(model_type, {})
                if m:
                    total = m.get("total_predictions", 50000)
                    prec = round(m.get("precision", 0.0), 4)
                    rec = round(m.get("recall", 0.0), 4)
                    tp = int(total * 0.02 * rec)
                    fn = int(total * 0.02 * (1 - rec))
                    fp = int(tp * (1 - prec) / prec) if prec > 0 else 50
                    tn = total - tp - fn - fp
                    real_metrics.append({
                        "model_version": f"{model_type.replace('_', ' ').title()} v{info.get('version', 'unknown')}",
                        "precision": prec,
                        "recall": rec,
                        "f1_score": round(m.get("f1_score", 0.0), 4),
                        "auc_roc": round(m.get("auc_roc", 0.0), 4),
                        "total_predictions": total,
                        "true_positives": tp,
                        "false_positives": fp,
                        "true_negatives": tn,
                        "false_negatives": fn,
                        "avg_latency_ms": round(m.get("avg_latency_ms", 25.0), 1),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
            if real_metrics:
                logger.info("ml_metrics_from_service", count=len(real_metrics))
                return APIResponse(data=real_metrics)

    # Fallback to mock
    return APIResponse(data=_mock_metrics())


@router.get("/ml/predictions")
async def list_predictions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List recent model predictions."""
    # No real-time prediction log endpoint on ML service — use mock
    predictions = _mock_predictions(page_size)
    return {
        "data": predictions,
        "total": 5000,
        "page": page,
        "page_size": page_size,
        "total_pages": 100,
    }


@router.get("/ml/models")
async def list_models():
    """List all registered model versions."""

    # Try to get model info from the real service
    info = await _ml_get("/model/info")
    if info is not None:
        ensemble_metrics = info.get("metrics", {})
        models = []
        for cfg in _MODEL_COMPARISON_STATIC:
            m = ensemble_metrics.get(cfg["model_type"], {})
            models.append({
                **cfg,
                "status": "active" if m else "available",
                "version": info.get("version", cfg["model_version"]),
                "metrics": {
                    "accuracy": round(m.get("accuracy", 0.0), 4),
                    "precision": round(m.get("precision", 0.0), 4),
                    "recall": round(m.get("recall", 0.0), 4),
                    "f1_score": round(m.get("f1_score", 0.0), 4),
                    "auc_roc": round(m.get("auc_roc", 0.0), 4),
                } if m else {},
            })
        logger.info("ml_models_from_service", count=len(models))
        return APIResponse(data=models)

    # Fallback: return static model list with mock metrics
    models = []
    for cfg in _MODEL_COMPARISON_STATIC:
        models.append({
            **cfg,
            "status": "available",
            "metrics": {
                "accuracy": round(random.uniform(0.92, 0.97), 4),
                "precision": round(random.uniform(0.90, 0.96), 4),
                "recall": round(random.uniform(0.85, 0.94), 4),
                "f1_score": round(random.uniform(0.88, 0.95), 4),
                "auc_roc": round(random.uniform(0.94, 0.99), 4),
            },
        })
    return APIResponse(data=models)


@router.post("/ml/predict")
async def predict_single(transaction: dict):
    """Proxy a single prediction to the ML service."""
    result = await _ml_post("/predict", transaction)
    if result is not None:
        return APIResponse(data=result)

    # Fallback: generate mock prediction
    fraud_prob = round(random.random(), 4)
    return APIResponse(data={
        "fraud_probability": fraud_prob,
        "risk_level": "HIGH" if fraud_prob > 0.85 else "MEDIUM" if fraud_prob > 0.6 else "LOW" if fraud_prob > 0.4 else "NONE",
        "model_version": "mock",
        "latency_ms": round(random.uniform(8, 50), 1),
        "timestamp": datetime.utcnow().isoformat(),
    })


@router.post("/ml/predict/batch")
async def predict_batch(payload: dict):
    """Proxy a batch prediction to the ML service."""
    result = await _ml_post("/predict/batch", payload)
    if result is not None:
        return APIResponse(data=result)

    # Fallback: mock batch
    count = len(payload.get("transactions", []))
    predictions = []
    for _ in range(count):
        fraud_prob = round(random.random(), 4)
        predictions.append({
            "fraud_probability": fraud_prob,
            "risk_level": "HIGH" if fraud_prob > 0.85 else "MEDIUM" if fraud_prob > 0.6 else "LOW" if fraud_prob > 0.4 else "NONE",
            "model_version": "mock",
            "latency_ms": round(random.uniform(8, 50), 1),
            "timestamp": datetime.utcnow().isoformat(),
        })
    return APIResponse(data={"predictions": predictions, "count": count})


@router.get("/ml/health")
async def ml_health():
    """Check ML service health."""
    result = await _ml_get("/health")
    if result is not None:
        return APIResponse(data={**result, "source": "ml-service"})
    return APIResponse(data={"status": "unreachable", "source": "mock"}, status="degraded")


@router.get("/ml/models/compare")
async def compare_models():
    """Return side-by-side metrics for all model types."""

    # Try real service
    info = await _ml_get("/model/info")
    if info is not None:
        ensemble_metrics = info.get("metrics", {})
        if ensemble_metrics:
            comparison = {}
            for model_type in ["xgboost", "random_forest", "isolation_forest", "ensemble"]:
                m = ensemble_metrics.get(model_type, {})
                comparison[model_type] = {
                    "model_name": model_type.replace("_", " ").title(),
                    "version": info.get("version", "unknown"),
                    "accuracy": round(m.get("accuracy", 0.0), 4),
                    "precision": round(m.get("precision", 0.0), 4),
                    "recall": round(m.get("recall", 0.0), 4),
                    "f1_score": round(m.get("f1_score", 0.0), 4),
                    "auc_roc": round(m.get("auc_roc", 0.0), 4),
                    "total_predictions": m.get("total_predictions", 0),
                    "avg_latency_ms": round(m.get("avg_latency_ms", 0.0), 1),
                }
            logger.info("ml_comparison_from_service")
            return APIResponse(data=comparison)

    # Fallback: mock comparison
    comparison = {}
    model_types = [
        ("xgboost", "XGBoost", "2.1.0"),
        ("random_forest", "Random Forest", "2.1.0"),
        ("isolation_forest", "Isolation Forest", "2.1.0"),
        ("ensemble", "Ensemble", "3.0.0"),
    ]
    for model_type, display_name, version in model_types:
        comparison[model_type] = {
            "model_name": display_name,
            "version": version,
            "accuracy": round(random.uniform(0.92, 0.97), 4),
            "precision": round(random.uniform(0.90, 0.96), 4),
            "recall": round(random.uniform(0.85, 0.94), 4),
            "f1_score": round(random.uniform(0.88, 0.95), 4),
            "auc_roc": round(random.uniform(0.94, 0.99), 4),
            "total_predictions": random.randint(30000, 60000),
            "avg_latency_ms": round(random.uniform(10, 40), 1),
        }
    return APIResponse(data=comparison)
