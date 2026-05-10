"""Fraud pattern definitions and scenario weights."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FraudType(str, Enum):
    """Types of fraud simulated by the platform."""
    CARD_TESTING = "card_testing"
    GEO_ANOMALY = "geo_anomaly"
    DEVICE_FRAUD = "device_fraud"
    MULE_ACCOUNT = "mule_account"
    ATM_FRAUD = "atm_fraud"
    ONLINE_FRAUD = "online_fraud"


@dataclass(frozen=True)
class FraudScenario:
    """Definition of a fraud scenario with risk characteristics."""
    fraud_type: FraudType
    description: str
    min_amount: float
    max_amount: float
    typical_risk_score: float  # 0-1 how suspicious this pattern is


# Predefined fraud scenarios
FRAUD_SCENARIOS: dict[FraudType, FraudScenario] = {
    FraudType.CARD_TESTING: FraudScenario(
        fraud_type=FraudType.CARD_TESTING,
        description="Rapid small-value transactions to verify stolen card details",
        min_amount=0.50,
        max_amount=5.00,
        typical_risk_score=0.85,
    ),
    FraudType.GEO_ANOMALY: FraudScenario(
        fraud_type=FraudType.GEO_ANOMALY,
        description="Transactions from impossible travel — locations >500km apart in <1 hour",
        min_amount=50.0,
        max_amount=2000.0,
        typical_risk_score=0.90,
    ),
    FraudType.DEVICE_FRAUD: FraudScenario(
        fraud_type=FraudType.DEVICE_FRAUD,
        description="Same customer ID used from unknown device and IP",
        min_amount=100.0,
        max_amount=3000.0,
        typical_risk_score=0.75,
    ),
    FraudType.MULE_ACCOUNT: FraudScenario(
        fraud_type=FraudType.MULE_ACCOUNT,
        description="Many small inbound transfers followed by large outbound withdrawal",
        min_amount=20.0,
        max_amount=5000.0,
        typical_risk_score=0.95,
    ),
    FraudType.ATM_FRAUD: FraudScenario(
        fraud_type=FraudType.ATM_FRAUD,
        description="High-value ATM withdrawals outside customer's usual area",
        min_amount=200.0,
        max_amount=500.0,
        typical_risk_score=0.70,
    ),
    FraudType.ONLINE_FRAUD: FraudScenario(
        fraud_type=FraudType.ONLINE_FRAUD,
        description="Online purchases with mismatched billing/shipping, high-risk merchants",
        min_amount=50.0,
        max_amount=5000.0,
        typical_risk_score=0.80,
    ),
}
