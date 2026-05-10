"""Fraud alert consumer for downstream processing.

Consumes from the fraud_alerts Kafka topic and forwards alerts to
downstream systems (e.g., notification service, case management).
"""

import json
import logging
import os
import signal
import sys
import time

from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("fraud_alert_consumer")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC = "fraud_alerts"
GROUP_ID = "fraud-alert-processor"

_shutdown = False


def _signal_handler(signum, frame):
    global _shutdown
    logger.info("Shutdown signal received.")
    _shutdown = True


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def handle_alert(alert: dict) -> None:
    """Process a single fraud alert.

    In production this would:
    - Send push notifications
    - Create case tickets
    - Trigger account freezes
    - Update real-time dashboards via WebSocket

    Args:
        alert: Parsed alert payload.
    """
    severity = alert.get("severity", "UNKNOWN")
    tx_id = alert.get("transaction_id", "N/A")
    customer = alert.get("customer_id", "N/A")
    amount = alert.get("amount", 0)
    score = alert.get("fraud_score", 0)
    action = alert.get("recommended_action", "NONE")

    logger.info(
        "ALERT [%s] tx=%s customer=%s amount=%.2f score=%.4f action=%s",
        severity,
        tx_id,
        customer,
        amount,
        score,
        action,
    )

    if severity == "HIGH":
        logger.warning(
            "HIGH SEVERITY: Immediate action required for customer %s, tx %s (score=%.4f)",
            customer,
            tx_id,
            score,
        )


def run_consumer() -> None:
    """Run the Kafka consumer loop."""
    logger.info("Starting fraud alert consumer (broker=%s, topic=%s)...", KAFKA_BROKER, TOPIC)

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BROKER.split(","),
        group_id=GROUP_ID,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        auto_commit_interval_ms=5000,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
        max_poll_records=100,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    logger.info("Consumer connected. Waiting for fraud alerts...")

    alert_count = 0
    high_count = 0
    start_time = time.time()

    try:
        while not _shutdown:
            messages = consumer.poll(timeout_ms=1000)

            for tp, records in messages.items():
                for record in records:
                    try:
                        handle_alert(record.value)
                        alert_count += 1
                        if record.value.get("severity") == "HIGH":
                            high_count += 1
                    except Exception as e:
                        logger.error(
                            "Failed to process alert at offset %d: %s",
                            record.offset,
                            e,
                        )

            # Periodic stats
            elapsed = time.time() - start_time
            if elapsed > 60:
                logger.info(
                    "Stats: %d alerts processed (%d HIGH) in last %.0fs",
                    alert_count,
                    high_count,
                    elapsed,
                )
                alert_count = 0
                high_count = 0
                start_time = time.time()

    finally:
        consumer.close()
        logger.info("Consumer closed.")


def main() -> None:
    """Entry point."""
    logger.info("=" * 50)
    logger.info("  Fraud Alert Consumer Service")
    logger.info("=" * 50)

    try:
        run_consumer()
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
