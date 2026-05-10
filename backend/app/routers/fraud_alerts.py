import uuid
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from app.models.schemas import (
    FraudAlertResponse,
    AlertUpdateRequest,
    AlertStatsResponse,
    APIResponse,
)

router = APIRouter()

CATEGORIES = [
    "Card Not Present", "Account Takeover", "Synthetic Identity",
    "Velocity Abuse", "Geo Anomaly", "Amount Anomaly",
    "Device Fingerprint Mismatch", "Cross-Border Fraud",
]
SEVERITIES = ["low", "medium", "high", "critical"]
ALERT_STATUSES = ["open", "investigating", "resolved", "false_positive"]
MERCHANTS = [
    "Amazon", "Walmart", "Target", "Starbucks", "Shell Gas",
    "Best Buy", "Netflix", "Uber", "DoorDash", "Apple Store",
]


def _generate_alert(i: int) -> FraudAlertResponse:
    score = round(random.uniform(0.4, 0.99), 4)
    if score > 0.85:
        severity = "critical"
    elif score > 0.6:
        severity = "high"
    elif score > 0.4:
        severity = "medium"
    else:
        severity = "low"

    category = random.choice(CATEGORIES)
    ts = datetime.utcnow() - timedelta(minutes=random.randint(0, 1440))

    return FraudAlertResponse(
        alert_id=f"ALT-{uuid.uuid4().hex[:12].upper()}",
        transaction_id=f"TXN-{uuid.uuid4().hex[:12].upper()}",
        customer_id=f"CUST-{random.randint(10000, 99999)}",
        merchant_name=random.choice(MERCHANTS),
        amount=round(random.uniform(50, 9999.99), 2),
        currency="USD",
        fraud_score=score,
        severity=severity,
        category=category,
        description=f"Suspicious {category.lower()} detected with confidence {score:.0%}",
        timestamp=ts.isoformat(),
        location_lat=round(random.uniform(25.0, 48.0), 6),
        location_lon=round(random.uniform(-124.0, -71.0), 6),
        status=random.choice(ALERT_STATUSES),
        features={
            "amount_zscore": round(random.uniform(-1, 5), 2),
            "velocity_1h": random.randint(1, 20),
            "distance_km": round(random.uniform(0, 5000), 1),
            "time_since_last_txn_min": random.randint(0, 480),
            "device_risk_score": round(random.uniform(0, 1), 3),
        },
    )


@router.get("/alerts")
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    """List fraud alerts with filtering."""
    alerts = [_generate_alert(i) for i in range(page_size)]

    if severity:
        alerts = [a for a in alerts if a.severity == severity]
    if status:
        alerts = [a for a in alerts if a.status == status]
    if search:
        s = search.lower()
        alerts = [a for a in alerts if s in a.customer_id.lower() or s in a.merchant_name.lower()]

    total = 500
    return {
        "data": [a.model_dump() for a in alerts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/alerts/stats")
async def alert_stats():
    """Alert statistics."""
    stats = AlertStatsResponse(
        total=random.randint(400, 600),
        open=random.randint(50, 100),
        investigating=random.randint(20, 50),
        resolved=random.randint(200, 350),
        false_positive=random.randint(30, 60),
        by_severity={
            "critical": random.randint(20, 50),
            "high": random.randint(80, 150),
            "medium": random.randint(150, 250),
            "low": random.randint(50, 100),
        },
        by_category={cat: random.randint(10, 80) for cat in CATEGORIES[:5]},
    )
    return APIResponse(data=stats.model_dump())


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    """Get single alert detail."""
    alert = _generate_alert(0)
    alert.alert_id = alert_id
    return APIResponse(data=alert.model_dump())


@router.put("/alerts/{alert_id}/status")
async def update_alert_status(alert_id: str, body: AlertUpdateRequest):
    """Update alert status."""
    if body.status not in ALERT_STATUSES:
        return APIResponse(data=None, message=f"Invalid status. Must be one of: {ALERT_STATUSES}")
    return APIResponse(
        data={"alert_id": alert_id, "status": body.status},
        message=f"Alert {alert_id} updated to {body.status}",
    )
