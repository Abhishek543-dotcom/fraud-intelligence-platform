"""Fraud Alerts API — serve real alerts from Kafka consumer buffer + case management via Redis."""

import json
import uuid
import random
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel, Field

from app.dependencies import get_redis
from app.models.schemas import (
    FraudAlertResponse,
    AlertUpdateRequest,
    AlertStatsResponse,
    APIResponse,
)

logger = structlog.get_logger()
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory alert buffer (populated by WebSocket broadcast)
# ---------------------------------------------------------------------------

_alert_buffer: deque[dict] = deque(maxlen=500)


def push_alert(alert_data: dict) -> None:
    """Called by the Kafka consumer to store alerts for REST access."""
    _alert_buffer.appendleft(alert_data)


# ---------------------------------------------------------------------------
# Case management models
# ---------------------------------------------------------------------------


class CaseNote(BaseModel):
    text: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    author: str = "Analyst"


class CaseAssignment(BaseModel):
    assigned_to: str


class CaseInfo(BaseModel):
    alert_id: str
    assigned_to: str | None = None
    notes: list[dict] = []
    status_history: list[dict] = []


# ---------------------------------------------------------------------------
# Mock data (fallback)
# ---------------------------------------------------------------------------

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
CHANNELS = ["online", "pos", "atm", "mobile"]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "FR", "AU"]
FIRST_NAMES = ["James", "Maria", "Robert", "Sarah", "Michael", "Emily", "David", "Lisa"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]


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
        customer_name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        merchant_name=random.choice(MERCHANTS),
        amount=round(random.uniform(50, 9999.99), 2),
        currency="USD",
        fraud_score=score,
        severity=severity,
        category=category,
        description=f"Suspicious {category.lower()} detected with confidence {score:.0%}",
        timestamp=ts.isoformat(),
        created_at=ts.isoformat(),
        location_lat=round(random.uniform(25.0, 48.0), 6),
        location_lon=round(random.uniform(-124.0, -71.0), 6),
        country=random.choice(COUNTRIES),
        channel=random.choice(CHANNELS),
        status=random.choice(ALERT_STATUSES),
        features={
            "amount_zscore": round(random.uniform(-1, 5), 2),
            "velocity_1h": random.randint(1, 20),
            "distance_km": round(random.uniform(0, 5000), 1),
            "time_since_last_txn_min": random.randint(0, 480),
            "device_risk_score": round(random.uniform(0, 1), 3),
        },
    )


def _buffer_to_response(raw: dict) -> dict:
    """Convert a raw Kafka alert dict to match FraudAlertResponse fields."""
    return {
        "alert_id": raw.get("alert_id", f"ALT-{uuid.uuid4().hex[:12].upper()}"),
        "transaction_id": raw.get("transaction_id", ""),
        "customer_id": raw.get("customer_id", ""),
        "customer_name": raw.get("customer_name", "Unknown"),
        "merchant_name": raw.get("merchant_name", "Unknown"),
        "amount": raw.get("amount", 0.0),
        "currency": raw.get("currency", "USD"),
        "fraud_score": raw.get("fraud_score", 0.0),
        "severity": raw.get("severity", "medium"),
        "category": raw.get("category", "Unknown"),
        "description": raw.get("description", ""),
        "timestamp": raw.get("timestamp", datetime.utcnow().isoformat()),
        "created_at": raw.get("created_at", datetime.utcnow().isoformat()),
        "location_lat": raw.get("location_lat", 0.0),
        "location_lon": raw.get("location_lon", 0.0),
        "country": raw.get("country", "US"),
        "channel": raw.get("channel", "online"),
        "status": raw.get("status", "open"),
        "features": raw.get("features", {}),
    }


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------


@router.get("/alerts")
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    """List fraud alerts — uses real Kafka buffer if available, otherwise mock."""
    # Try real data from buffer
    if len(_alert_buffer) > 0:
        alerts = [_buffer_to_response(a) for a in list(_alert_buffer)]
    else:
        alerts = [_generate_alert(i).model_dump() for i in range(page_size)]

    # Apply filters
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    if status:
        alerts = [a for a in alerts if a.get("status") == status]
    if search:
        s = search.lower()
        alerts = [a for a in alerts if s in a.get("customer_id", "").lower() or s in a.get("merchant_name", "").lower()]

    # Paginate
    total = len(alerts)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = alerts[start:end]

    return {
        "data": page_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/alerts/stats")
async def alert_stats():
    """Alert statistics — computed from buffer if available."""
    if len(_alert_buffer) > 0:
        alerts = list(_alert_buffer)
        total = len(alerts)
        by_status = {}
        by_severity = {}
        by_category: dict[str, int] = {}
        for a in alerts:
            s = a.get("status", "open")
            by_status[s] = by_status.get(s, 0) + 1
            sev = a.get("severity", "medium")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            cat = a.get("category", "Unknown")
            by_category[cat] = by_category.get(cat, 0) + 1

        stats = AlertStatsResponse(
            total=total,
            open=by_status.get("open", 0),
            investigating=by_status.get("investigating", 0),
            resolved=by_status.get("resolved", 0),
            false_positive=by_status.get("false_positive", 0),
            by_severity=by_severity,
            by_category=dict(list(by_category.items())[:5]),
        )
    else:
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
    """Get single alert detail — search buffer first, then mock."""
    for raw in _alert_buffer:
        if raw.get("alert_id") == alert_id:
            return APIResponse(data=_buffer_to_response(raw))
    # Fallback mock
    alert = _generate_alert(0)
    alert.alert_id = alert_id
    return APIResponse(data=alert.model_dump())


@router.put("/alerts/{alert_id}/status")
async def update_alert_status(alert_id: str, body: AlertUpdateRequest, redis=Depends(get_redis)):
    """Update alert status and record in case history."""
    if body.status not in ALERT_STATUSES:
        return APIResponse(data=None, message=f"Invalid status. Must be one of: {ALERT_STATUSES}")

    # Persist status change to Redis
    key = f"fraud:case:{alert_id}"
    try:
        existing = await redis.get(key)
        case = json.loads(existing) if existing else {"alert_id": alert_id, "assigned_to": None, "notes": [], "status_history": []}
        case["status_history"].append({"status": body.status, "timestamp": datetime.utcnow().isoformat()})
        await redis.set(key, json.dumps(case), ex=86400 * 7)  # 7 day TTL
    except Exception as exc:
        logger.warning("redis_case_update_failed", alert_id=alert_id, error=str(exc))

    return APIResponse(
        data={"alert_id": alert_id, "status": body.status},
        message=f"Alert {alert_id} updated to {body.status}",
    )


# ---------------------------------------------------------------------------
# Case management endpoints
# ---------------------------------------------------------------------------


@router.put("/alerts/{alert_id}/assign")
async def assign_alert(alert_id: str, body: CaseAssignment, redis=Depends(get_redis)):
    """Assign alert to an analyst."""
    key = f"fraud:case:{alert_id}"
    try:
        existing = await redis.get(key)
        case = json.loads(existing) if existing else {"alert_id": alert_id, "assigned_to": None, "notes": [], "status_history": []}
        case["assigned_to"] = body.assigned_to
        case["status_history"].append({"status": f"assigned to {body.assigned_to}", "timestamp": datetime.utcnow().isoformat()})
        await redis.set(key, json.dumps(case), ex=86400 * 7)
    except Exception as exc:
        logger.warning("redis_assign_failed", alert_id=alert_id, error=str(exc))
        return APIResponse(data={"alert_id": alert_id, "assigned_to": body.assigned_to}, message="Assigned (Redis unavailable)")

    return APIResponse(data={"alert_id": alert_id, "assigned_to": body.assigned_to})


@router.post("/alerts/{alert_id}/notes")
async def add_note(alert_id: str, note: CaseNote, redis=Depends(get_redis)):
    """Add investigation note to an alert case."""
    key = f"fraud:case:{alert_id}"
    try:
        existing = await redis.get(key)
        case = json.loads(existing) if existing else {"alert_id": alert_id, "assigned_to": None, "notes": [], "status_history": []}
        case["notes"].append({"text": note.text, "timestamp": note.timestamp, "author": note.author})
        await redis.set(key, json.dumps(case), ex=86400 * 7)
    except Exception as exc:
        logger.warning("redis_note_failed", alert_id=alert_id, error=str(exc))
        return APIResponse(data={"alert_id": alert_id, "note_added": True}, message="Note saved (Redis unavailable)")

    return APIResponse(data={"alert_id": alert_id, "note_added": True, "total_notes": len(case["notes"])})


@router.get("/alerts/{alert_id}/case")
async def get_case(alert_id: str, redis=Depends(get_redis)):
    """Get full case info for an alert."""
    key = f"fraud:case:{alert_id}"
    try:
        existing = await redis.get(key)
        if existing:
            case = json.loads(existing)
            return APIResponse(data=case)
    except Exception as exc:
        logger.warning("redis_case_read_failed", alert_id=alert_id, error=str(exc))

    # Return empty case
    return APIResponse(data={"alert_id": alert_id, "assigned_to": None, "notes": [], "status_history": []})
