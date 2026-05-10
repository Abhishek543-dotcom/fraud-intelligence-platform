"""Configuration for the transaction simulator and Kafka producer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimulatorConfig:
    """Transaction simulator configuration."""

    # Throughput
    target_tps: int = int(os.getenv("TARGET_TPS", "100"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "100"))

    # Pool sizes
    num_customers: int = int(os.getenv("NUM_CUSTOMERS", "10000"))
    num_merchants: int = int(os.getenv("NUM_MERCHANTS", "5000"))

    # Fraud settings
    fraud_ratio: float = float(os.getenv("FRAUD_RATIO", "0.02"))

    # Weighted fraud type distribution
    fraud_weights: dict[str, float] = field(default_factory=lambda: {
        "card_testing": 0.25,
        "geo_anomaly": 0.20,
        "device_fraud": 0.15,
        "mule_account": 0.15,
        "atm_fraud": 0.10,
        "online_fraud": 0.15,
    })


@dataclass(frozen=True)
class KafkaConfig:
    """Kafka producer configuration."""

    bootstrap_servers: str = os.getenv("KAFKA_BROKER", "localhost:9094")

    # Topics
    topic_raw: str = "transactions_raw"
    topic_dlq: str = "dlq_transactions"
    topic_alerts: str = "fraud_alerts"

    # Producer tuning
    compression_type: str = "snappy"
    batch_size: int = 16384
    linger_ms: int = 10
    max_retries: int = 5
    retry_backoff_ms: int = 100
    enable_idempotence: bool = True
    acks: str = "all"
    request_timeout_ms: int = 30000
    max_in_flight_requests: int = 5


@dataclass(frozen=True)
class MetricsConfig:
    """Metrics reporting configuration."""

    log_interval_seconds: int = 10
    prometheus_port: int = int(os.getenv("METRICS_PORT", "9100"))


# Singleton instances
SIMULATOR_CONFIG = SimulatorConfig()
KAFKA_CONFIG = KafkaConfig()
METRICS_CONFIG = MetricsConfig()
