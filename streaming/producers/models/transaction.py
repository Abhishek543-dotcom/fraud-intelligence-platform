"""Transaction Pydantic models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    """Supported transaction types."""
    CARD_SWIPE = "CARD_SWIPE"
    ATM_WITHDRAWAL = "ATM_WITHDRAWAL"
    ONLINE_PURCHASE = "ONLINE_PURCHASE"
    WIRE_TRANSFER = "WIRE_TRANSFER"
    P2P = "P2P"


class Channel(str, Enum):
    """Transaction channel."""
    POS = "POS"
    ATM = "ATM"
    WEB = "WEB"
    MOBILE = "MOBILE"
    BRANCH = "BRANCH"


class AuthMethod(str, Enum):
    """Authentication methods."""
    CHIP = "CHIP"
    SWIPE = "SWIPE"
    CONTACTLESS = "CONTACTLESS"
    PIN = "PIN"
    PASSWORD = "PASSWORD"
    BIOMETRIC = "BIOMETRIC"
    TWO_FACTOR = "TWO_FACTOR"
    NONE = "NONE"


class Transaction(BaseModel):
    """Core transaction event model.

    Represents a single financial transaction flowing through
    the fraud detection pipeline.
    """
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str
    merchant_id: str
    amount: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(default="USD", max_length=3, description="ISO 4217 currency code")
    transaction_type: TransactionType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    merchant_category: str = Field(description="MCC code")
    merchant_name: str
    merchant_country: str
    merchant_city: str
    customer_lat: float = Field(ge=-90, le=90)
    customer_lon: float = Field(ge=-180, le=180)
    device_id: str
    device_fingerprint: str
    ip_address: str
    channel: Channel
    is_international: bool = False
    card_present: bool = True
    authentication_method: AuthMethod = AuthMethod.CHIP
    risk_indicators: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    is_fraud: bool = False
    fraud_type: Optional[str] = None

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }

    def to_kafka_dict(self) -> dict:
        """Serialize to dict suitable for Kafka JSON encoding."""
        data = self.model_dump()
        data["amount"] = float(data["amount"])
        data["timestamp"] = data["timestamp"].isoformat()
        return data
