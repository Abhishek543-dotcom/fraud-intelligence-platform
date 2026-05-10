import asyncio
import json
import uuid
import random
from datetime import datetime

import structlog

logger = structlog.get_logger()

CATEGORIES = [
    "Card Not Present", "Account Takeover", "Synthetic Identity",
    "Velocity Abuse", "Geo Anomaly", "Amount Anomaly",
]
MERCHANTS = [
    "Amazon", "Walmart", "Target", "Starbucks", "Shell Gas",
    "Best Buy", "Netflix", "Uber", "DoorDash", "Apple Store",
]


class KafkaAlertConsumer:
    """Background Kafka consumer that reads fraud_alerts and broadcasts via WebSocket."""

    def __init__(self, broker: str, topic: str, ws_manager):
        self.broker = broker
        self.topic = topic
        self.ws_manager = ws_manager
        self._running = False
        self._consumer = None

    async def start(self) -> None:
        """Start consuming from Kafka. Falls back to simulated alerts if Kafka is unavailable."""
        self._running = True
        logger.info("kafka_consumer_starting", broker=self.broker, topic=self.topic)

        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.broker,
                group_id="backend-ws-consumer",
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                max_poll_interval_ms=300000,
                session_timeout_ms=30000,
            )
            await self._consumer.start()
            logger.info("kafka_consumer_connected")

            async for message in self._consumer:
                if not self._running:
                    break
                try:
                    alert_data = message.value
                    await self.ws_manager.broadcast({
                        "type": "alert",
                        "data": alert_data,
                    })
                except Exception as e:
                    logger.error("kafka_message_error", error=str(e))

        except Exception as e:
            logger.warning("kafka_unavailable_using_simulator", error=str(e))
            await self._simulate_alerts()

    async def _simulate_alerts(self) -> None:
        """Generate simulated alerts when Kafka is not available."""
        logger.info("starting_simulated_alert_feed")
        while self._running:
            await asyncio.sleep(random.uniform(2, 8))
            if not self._running:
                break

            score = round(random.uniform(0.3, 0.99), 4)
            if score > 0.85:
                severity = "critical"
            elif score > 0.6:
                severity = "high"
            elif score > 0.4:
                severity = "medium"
            else:
                severity = "low"

            category = random.choice(CATEGORIES)
            alert = {
                "alert_id": f"ALT-{uuid.uuid4().hex[:12].upper()}",
                "transaction_id": f"TXN-{uuid.uuid4().hex[:12].upper()}",
                "customer_id": f"CUST-{random.randint(10000, 99999)}",
                "merchant_name": random.choice(MERCHANTS),
                "amount": round(random.uniform(50, 9999.99), 2),
                "currency": "USD",
                "fraud_score": score,
                "severity": severity,
                "category": category,
                "description": f"Suspicious {category.lower()} detected with confidence {score:.0%}",
                "timestamp": datetime.utcnow().isoformat(),
                "location_lat": round(random.uniform(25.0, 48.0), 6),
                "location_lon": round(random.uniform(-124.0, -71.0), 6),
                "status": "open",
                "features": {
                    "amount_zscore": round(random.uniform(-1, 5), 2),
                    "velocity_1h": random.randint(1, 20),
                    "distance_km": round(random.uniform(0, 5000), 1),
                },
            }

            await self.ws_manager.broadcast({"type": "alert", "data": alert})

            # Periodically send metric updates
            if random.random() < 0.3:
                await self.ws_manager.broadcast({
                    "type": "metric",
                    "data": {
                        "total_transactions_24h": random.randint(80000, 120000),
                        "fraud_detected_24h": random.randint(200, 500),
                        "amount_blocked_24h": round(random.uniform(50000, 250000), 2),
                        "false_positive_rate": round(random.uniform(0.02, 0.08), 4),
                        "avg_inference_time_ms": round(random.uniform(15, 45), 1),
                    },
                })

    def stop(self) -> None:
        self._running = False
        logger.info("kafka_consumer_stopping")

    async def close(self) -> None:
        self.stop()
        if self._consumer:
            await self._consumer.stop()
