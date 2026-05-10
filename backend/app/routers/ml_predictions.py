import random
from datetime import datetime

from fastapi import APIRouter, Query
from app.models.schemas import (
    ModelMetricsResponse,
    APIResponse,
)

router = APIRouter()

MODEL_CONFIGS = [
    ("XGBoost", "2.1.0"),
    ("LightGBM", "1.3.0"),
    ("Ensemble", "3.0.0"),
]


@router.get("/ml/metrics")
async def model_metrics():
    """Get ML model performance metrics."""
    metrics = []
    for name, version in MODEL_CONFIGS:
        metrics.append(
            ModelMetricsResponse(
                model_name=name,
                model_version=version,
                accuracy=round(random.uniform(0.92, 0.97), 4),
                precision=round(random.uniform(0.90, 0.96), 4),
                recall=round(random.uniform(0.85, 0.94), 4),
                f1_score=round(random.uniform(0.88, 0.95), 4),
                auc_roc=round(random.uniform(0.94, 0.99), 4),
                total_predictions=random.randint(30000, 60000),
                timestamp=datetime.utcnow().isoformat(),
            ).model_dump()
        )
    return APIResponse(data=metrics)


@router.get("/ml/predictions")
async def list_predictions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List recent model predictions."""
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

    return {
        "data": predictions,
        "total": 5000,
        "page": page,
        "page_size": page_size,
        "total_pages": 100,
    }
