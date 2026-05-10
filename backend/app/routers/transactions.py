import uuid
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from app.models.schemas import (
    TransactionResponse,
    TransactionListResponse,
    APIResponse,
    MetricOverview,
)

router = APIRouter()

# In-memory sample data generator for demonstration
CHANNELS = ["online", "pos", "atm", "mobile"]
CARD_TYPES = ["visa", "mastercard", "amex", "discover"]
MERCHANTS = [
    "Amazon", "Walmart", "Target", "Starbucks", "Shell Gas",
    "Best Buy", "Netflix", "Uber", "DoorDash", "Apple Store",
    "Home Depot", "Costco", "Whole Foods", "CVS Pharmacy", "McDonald's",
]
STATUSES = ["approved", "declined", "flagged", "pending"]


def _generate_transaction(i: int) -> TransactionResponse:
    ts = datetime.utcnow() - timedelta(minutes=random.randint(0, 1440))
    amount = round(random.uniform(1.50, 9999.99), 2)
    score = random.random()
    is_fraud = score > 0.75
    return TransactionResponse(
        transaction_id=f"TXN-{uuid.uuid4().hex[:12].upper()}",
        customer_id=f"CUST-{random.randint(10000, 99999)}",
        merchant_id=f"MERCH-{random.randint(1000, 9999)}",
        merchant_name=random.choice(MERCHANTS),
        amount=amount,
        currency="USD",
        timestamp=ts.isoformat(),
        channel=random.choice(CHANNELS),
        location_lat=round(random.uniform(25.0, 48.0), 6),
        location_lon=round(random.uniform(-124.0, -71.0), 6),
        card_type=random.choice(CARD_TYPES),
        is_international=random.random() < 0.1,
        fraud_score=round(score, 4),
        is_fraud=is_fraud,
        status="flagged" if is_fraud else random.choice(["approved", "approved", "approved", "pending"]),
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    customer_id: str | None = None,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    status: str | None = None,
):
    """List transactions with filtering and pagination."""
    total = 1000
    transactions = [_generate_transaction(i) for i in range(page_size)]

    if search:
        s = search.lower()
        transactions = [
            t for t in transactions
            if s in t.customer_id.lower() or s in t.merchant_name.lower() or s in t.transaction_id.lower()
        ]
    if customer_id:
        transactions = [t for t in transactions if t.customer_id == customer_id]
    if merchant:
        transactions = [t for t in transactions if merchant.lower() in t.merchant_name.lower()]
    if min_amount is not None:
        transactions = [t for t in transactions if t.amount >= min_amount]
    if max_amount is not None:
        transactions = [t for t in transactions if t.amount <= max_amount]
    if status:
        transactions = [t for t in transactions if t.status == status]

    return TransactionListResponse(
        data=transactions,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/transactions/stats")
async def transaction_stats():
    """Aggregated transaction statistics."""
    return APIResponse(
        data=MetricOverview(
            total_transactions_24h=random.randint(80000, 120000),
            fraud_detected_24h=random.randint(200, 500),
            amount_blocked_24h=round(random.uniform(50000, 250000), 2),
            false_positive_rate=round(random.uniform(0.02, 0.08), 4),
            avg_inference_time_ms=round(random.uniform(15, 45), 1),
        ).model_dump(),
    )


@router.get("/transactions/{transaction_id}")
async def get_transaction(transaction_id: str):
    """Get single transaction detail."""
    tx = _generate_transaction(0)
    tx.transaction_id = transaction_id
    return APIResponse(data=tx.model_dump())
