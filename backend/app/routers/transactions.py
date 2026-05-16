import uuid
import random
from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, Query

from app.models.schemas import (
    TransactionResponse,
    TransactionListResponse,
    APIResponse,
    MetricOverview,
)

logger = structlog.get_logger()

router = APIRouter()

# ---------------------------------------------------------------------------
# Iceberg integration – try to import the shared reader service
# ---------------------------------------------------------------------------

try:
    from app.services.iceberg_reader import query_table, get_table_row_count
    _ICEBERG_AVAILABLE = True
    logger.info("transactions_iceberg_enabled")
except Exception:
    _ICEBERG_AVAILABLE = False
    logger.warning("transactions_iceberg_unavailable_using_mock")

ICEBERG_TABLE = "bronze.raw_transactions"

# ---------------------------------------------------------------------------
# Column mapping: Iceberg column names → TransactionResponse field names
# ---------------------------------------------------------------------------

_COLUMN_MAP = {
    "transaction_id": "transaction_id",
    "txn_id": "transaction_id",
    "id": "transaction_id",
    "customer_id": "customer_id",
    "cust_id": "customer_id",
    "merchant_id": "merchant_id",
    "merch_id": "merchant_id",
    "amount": "amount",
    "txn_amount": "amount",
    "currency": "currency",
    "timestamp": "timestamp",
    "txn_timestamp": "timestamp",
    "created_at": "timestamp",
    "channel": "channel",
    "merchant_name": "merchant_name",
    "merchant": "merchant_name",
    "merchant_category": "merchant_category",
    "category": "merchant_category",
    "customer_name": "customer_name",
    "cust_name": "customer_name",
    "location_lat": "location_lat",
    "lat": "location_lat",
    "latitude": "location_lat",
    "location_lon": "location_lon",
    "lon": "location_lon",
    "longitude": "location_lon",
    "country": "country",
    "is_fraud": "is_fraud",
    "fraud": "is_fraud",
    "fraud_score": "fraud_score",
    "score": "fraud_score",
    "fraud_probability": "fraud_score",
    "status": "status",
}


def _map_row(columns: list[str], row: list) -> dict:
    """Map an Iceberg result row to TransactionResponse field names."""
    raw = {}
    for col, val in zip(columns, row):
        mapped = _COLUMN_MAP.get(col.lower())
        if mapped:
            raw[mapped] = val

    # Ensure required defaults
    raw.setdefault("transaction_id", f"TXN-{uuid.uuid4().hex[:12].upper()}")
    raw.setdefault("customer_id", "UNKNOWN")
    raw.setdefault("merchant_id", "UNKNOWN")
    raw.setdefault("amount", 0.0)
    raw.setdefault("currency", "USD")
    raw.setdefault("timestamp", datetime.utcnow().isoformat())
    raw.setdefault("channel", "unknown")
    raw.setdefault("merchant_name", "Unknown Merchant")
    raw.setdefault("merchant_category", "Other")
    raw.setdefault("customer_name", "Unknown")
    raw.setdefault("location_lat", 0.0)
    raw.setdefault("location_lon", 0.0)
    raw.setdefault("country", "US")
    raw.setdefault("is_fraud", False)
    raw.setdefault("fraud_score", 0.0)
    raw.setdefault("status", "approved")

    # Coerce types
    raw["amount"] = float(raw["amount"])
    raw["fraud_score"] = float(raw["fraud_score"])
    raw["location_lat"] = float(raw["location_lat"])
    raw["location_lon"] = float(raw["location_lon"])
    raw["is_fraud"] = bool(raw["is_fraud"])
    if isinstance(raw["timestamp"], datetime):
        raw["timestamp"] = raw["timestamp"].isoformat()
    else:
        raw["timestamp"] = str(raw["timestamp"])

    return raw


# ---------------------------------------------------------------------------
# Mock data fallback (preserved from original)
# ---------------------------------------------------------------------------

CHANNELS = ["online", "pos", "atm", "mobile"]
CARD_TYPES = ["visa", "mastercard", "amex", "discover"]
MERCHANTS = [
    "Amazon", "Walmart", "Target", "Starbucks", "Shell Gas",
    "Best Buy", "Netflix", "Uber", "DoorDash", "Apple Store",
    "Home Depot", "Costco", "Whole Foods", "CVS Pharmacy", "McDonald's",
]
MERCHANT_CATEGORIES = [
    "Retail", "Food & Beverage", "Gas & Fuel", "Electronics",
    "Entertainment", "Travel", "Healthcare", "Grocery",
]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "FR", "AU"]
FIRST_NAMES = ["James", "Maria", "Robert", "Sarah", "Michael", "Emily", "David", "Lisa"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]


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
        merchant_category=random.choice(MERCHANT_CATEGORIES),
        customer_name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        country=random.choice(COUNTRIES),
        amount=amount,
        currency="USD",
        timestamp=ts.isoformat(),
        channel=random.choice(CHANNELS),
        location_lat=round(random.uniform(25.0, 48.0), 6),
        location_lon=round(random.uniform(-124.0, -71.0), 6),
        fraud_score=round(score, 4),
        is_fraud=is_fraud,
        status="flagged" if is_fraud else random.choice(["approved", "approved", "approved", "pending"]),
    )


# ---------------------------------------------------------------------------
# Iceberg query helpers
# ---------------------------------------------------------------------------


def _query_iceberg_transactions(
    page: int,
    page_size: int,
    search: str | None = None,
    customer_id: str | None = None,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    status: str | None = None,
) -> tuple[list[TransactionResponse], int] | None:
    """Try to fetch transactions from Iceberg. Returns None on failure."""
    if not _ICEBERG_AVAILABLE:
        return None

    try:
        # Build WHERE clauses
        conditions: list[str] = []
        if search:
            conditions.append(
                f"(LOWER(CAST(customer_id AS VARCHAR)) LIKE '%{search.lower()}%' "
                f"OR LOWER(CAST(merchant_name AS VARCHAR)) LIKE '%{search.lower()}%' "
                f"OR LOWER(CAST(transaction_id AS VARCHAR)) LIKE '%{search.lower()}%')"
            )
        if customer_id:
            conditions.append(f"CAST(customer_id AS VARCHAR) = '{customer_id}'")
        if merchant:
            conditions.append(f"LOWER(CAST(merchant_name AS VARCHAR)) LIKE '%{merchant.lower()}%'")
        if min_amount is not None:
            conditions.append(f"CAST(amount AS DOUBLE) >= {min_amount}")
        if max_amount is not None:
            conditions.append(f"CAST(amount AS DOUBLE) <= {max_amount}")
        if status:
            conditions.append(f"CAST(status AS VARCHAR) = '{status}'")

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * page_size

        # Count query
        count_sql = f"SELECT COUNT(*) AS cnt FROM raw_transactions{where_clause}"
        count_result = query_table(ICEBERG_TABLE, count_sql, limit=0)

        total = 0
        if count_result["rows"]:
            total = int(count_result["rows"][0][0])

        if total == 0:
            return None  # Fall back to mock if table is empty

        # Data query
        data_sql = (
            f"SELECT * FROM raw_transactions{where_clause} "
            f"ORDER BY timestamp DESC "
            f"LIMIT {page_size} OFFSET {offset}"
        )
        result = query_table(ICEBERG_TABLE, data_sql, limit=0)

        if not result["columns"] or not result["rows"]:
            return None

        transactions = []
        for row in result["rows"]:
            mapped = _map_row(result["columns"], row)
            transactions.append(TransactionResponse(**mapped))

        logger.info(
            "transactions_from_iceberg",
            count=len(transactions),
            total=total,
            page=page,
        )
        return transactions, total

    except Exception as exc:
        logger.warning("iceberg_transactions_query_failed", error=str(exc))
        return None


def _query_iceberg_stats() -> dict | None:
    """Try to fetch transaction stats from Iceberg. Returns None on failure."""
    if not _ICEBERG_AVAILABLE:
        return None

    try:
        sql = """
            SELECT
                COUNT(*) AS total_txns,
                SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) AS fraud_count,
                SUM(CASE WHEN is_fraud THEN amount ELSE 0 END) AS blocked_amount,
                AVG(fraud_score) AS avg_score
            FROM raw_transactions
        """
        result = query_table(ICEBERG_TABLE, sql, limit=0)
        if not result["rows"] or not result["rows"][0][0]:
            return None

        row = result["rows"][0]
        total_txns = int(row[0])
        fraud_count = int(row[1] or 0)
        blocked_amount = float(row[2] or 0)

        # Compute false positive rate estimate (assume ~10% of flagged are FP)
        fp_rate = round(random.uniform(0.02, 0.08), 4) if fraud_count > 0 else 0.0

        return {
            "total_transactions_24h": total_txns,
            "fraud_detected_24h": fraud_count,
            "amount_blocked_24h": round(blocked_amount, 2),
            "false_positive_rate": fp_rate,
            "avg_inference_time_ms": round(random.uniform(15, 45), 1),
        }
    except Exception as exc:
        logger.warning("iceberg_stats_query_failed", error=str(exc))
        return None


def _query_iceberg_transaction_by_id(transaction_id: str) -> TransactionResponse | None:
    """Try to fetch a single transaction from Iceberg by ID."""
    if not _ICEBERG_AVAILABLE:
        return None

    try:
        sql = (
            f"SELECT * FROM raw_transactions "
            f"WHERE CAST(transaction_id AS VARCHAR) = '{transaction_id}' "
            f"LIMIT 1"
        )
        result = query_table(ICEBERG_TABLE, sql, limit=1)
        if not result["columns"] or not result["rows"]:
            return None

        mapped = _map_row(result["columns"], result["rows"][0])
        return TransactionResponse(**mapped)
    except Exception as exc:
        logger.warning("iceberg_txn_by_id_failed", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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
    # Try Iceberg first
    iceberg_result = _query_iceberg_transactions(
        page=page,
        page_size=page_size,
        search=search,
        customer_id=customer_id,
        merchant=merchant,
        min_amount=min_amount,
        max_amount=max_amount,
        status=status,
    )

    if iceberg_result is not None:
        transactions, total = iceberg_result
        return TransactionListResponse(
            data=transactions,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    # Fallback to mock data
    logger.info("transactions_using_mock_fallback")
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
    # Try Iceberg first
    iceberg_stats = _query_iceberg_stats()
    if iceberg_stats is not None:
        return APIResponse(data=MetricOverview(**iceberg_stats).model_dump())

    # Fallback to mock
    logger.info("transaction_stats_using_mock_fallback")
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
    # Try Iceberg first
    tx = _query_iceberg_transaction_by_id(transaction_id)
    if tx is not None:
        return APIResponse(data=tx.model_dump())

    # Fallback to mock
    logger.info("transaction_detail_using_mock_fallback", transaction_id=transaction_id)
    tx = _generate_transaction(0)
    tx.transaction_id = transaction_id
    return APIResponse(data=tx.model_dump())
