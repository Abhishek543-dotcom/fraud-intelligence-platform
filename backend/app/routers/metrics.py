import random
from datetime import datetime

from fastapi import APIRouter
from app.models.schemas import APIResponse, MetricOverview

router = APIRouter()


@router.get("/metrics/overview")
async def metrics_overview():
    """System metrics overview."""
    return APIResponse(
        data=MetricOverview(
            total_transactions_24h=random.randint(80000, 120000),
            fraud_detected_24h=random.randint(200, 500),
            amount_blocked_24h=round(random.uniform(50000, 250000), 2),
            false_positive_rate=round(random.uniform(0.02, 0.08), 4),
            avg_inference_time_ms=round(random.uniform(15, 45), 1),
        ).model_dump(),
    )


@router.get("/metrics/kafka")
async def kafka_metrics():
    """Kafka throughput metrics."""
    topics = {
        "transactions_raw": random.randint(30, 80),
        "transactions_enriched": random.randint(25, 70),
        "fraud_alerts": random.randint(1, 10),
        "model_predictions": random.randint(25, 70),
    }
    return APIResponse(
        data={
            "topics": topics,
            "total_messages_per_second": sum(topics.values()),
            "consumer_lag": {k: random.randint(0, 100) for k in topics},
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


@router.get("/metrics/system")
async def system_metrics():
    """System resource metrics."""
    return APIResponse(
        data={
            "services": {
                "kafka": {"status": "healthy", "uptime_hours": random.randint(1, 720)},
                "spark": {"status": "healthy", "active_jobs": random.randint(0, 3)},
                "minio": {"status": "healthy", "storage_used_gb": round(random.uniform(0.5, 10), 2)},
                "redis": {"status": "healthy", "memory_used_mb": random.randint(20, 80)},
                "postgres": {"status": "healthy", "connections": random.randint(5, 20)},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
