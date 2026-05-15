from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime


class TransactionResponse(BaseModel):
    transaction_id: str
    customer_id: str
    merchant_id: str
    amount: float
    currency: str = "USD"
    timestamp: str
    channel: str
    merchant_name: str
    merchant_category: str
    customer_name: str
    location_lat: float
    location_lon: float
    country: str
    is_fraud: bool
    fraud_score: float
    status: str


class FraudAlertResponse(BaseModel):
    alert_id: str
    transaction_id: str
    customer_id: str
    fraud_score: float
    severity: str
    status: str
    amount: float
    currency: str = "USD"
    merchant_name: str
    customer_name: str
    location_lat: float
    location_lon: float
    country: str
    channel: str
    category: Optional[str] = None
    description: Optional[str] = None
    features: Dict[str, float] = {}
    timestamp: str
    created_at: str


class AlertUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        description="New status: open, investigating, resolved, false_positive",
    )


class PredictionResponse(BaseModel):
    prediction_id: str
    transaction_id: str
    model_version: str
    fraud_probability: float
    is_fraud: bool
    features: Dict[str, float] = {}
    explanation: List[str] = []
    latency_ms: float
    timestamp: Optional[str] = None


class ModelMetrics(BaseModel):
    model_version: str
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    total_predictions: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    avg_latency_ms: float
    timestamp: str


class DashboardMetrics(BaseModel):
    total_transactions_24h: int = 0
    total_transactions_trend: float = 0.0
    fraud_detected_24h: int = 0
    fraud_detected_trend: float = 0.0
    amount_blocked_24h: float = 0.0
    amount_blocked_trend: float = 0.0
    false_positive_rate: float = 0.0
    false_positive_trend: float = 0.0
    avg_detection_time_ms: float = 0.0
    active_alerts: int = 0


class InvestigationRequest(BaseModel):
    message: str
    alert_id: Optional[str] = None
    context: Optional[Dict[str, str]] = None
    notes: Optional[str] = None


class InvestigationResponse(BaseModel):
    data: str
    message: Optional[str] = None


class WebSocketMessage(BaseModel):
    type: str  # alert | metric | heartbeat
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class PaginatedResponse(BaseModel):
    data: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class APIResponse(BaseModel):
    data: Any
    status: str = "success"
    message: Optional[str] = None


class FilterParams(BaseModel):
    page: int = 1
    page_size: int = 50
    sort_by: str = "timestamp"
    sort_order: str = "desc"
    search: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    severity: Optional[str] = None
    status: Optional[str] = None


class TransactionListResponse(BaseModel):
    data: List[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MetricOverview(BaseModel):
    total_transactions_24h: int
    fraud_detected_24h: int
    amount_blocked_24h: float
    false_positive_rate: float
    avg_inference_time_ms: float


class AlertStatsResponse(BaseModel):
    total: int
    open: int
    investigating: int
    resolved: int
    false_positive: int
    by_severity: Dict[str, int]
    by_category: Dict[str, int]


class ModelMetricsResponse(BaseModel):
    model_name: str
    model_version: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    total_predictions: int
    timestamp: str
