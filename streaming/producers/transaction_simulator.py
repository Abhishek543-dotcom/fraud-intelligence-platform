"""Main transaction simulator — AsyncIO event loop producing transactions to Kafka."""

from __future__ import annotations

import asyncio
import random
import signal
import time
from datetime import datetime, timezone

import structlog

from .config import KAFKA_CONFIG, METRICS_CONFIG, SIMULATOR_CONFIG
from .generators.atm_withdrawal import ATMWithdrawalGenerator
from .generators.burst_fraud import BurstFraudGenerator
from .generators.card_swipe import CardSwipeGenerator
from .generators.device_mismatch import DeviceMismatchGenerator
from .generators.geo_anomaly import GeoAnomalyGenerator
from .generators.mule_account import MuleAccountGenerator
from .generators.online_purchase import OnlinePurchaseGenerator
from .kafka_producer import FraudKafkaProducer
from .models.customer import CustomerProfile
from .models.merchant import MerchantProfile

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
)

logger = structlog.get_logger("simulator")


class TransactionSimulator:
    """High-throughput transaction simulator driving the fraud detection pipeline.

    Generates a mix of legitimate and fraudulent transactions at a
    configurable TPS rate and streams them into Kafka.
    """

    def __init__(self) -> None:
        self._config = SIMULATOR_CONFIG
        self._shutdown_event = asyncio.Event()
        self._producer = FraudKafkaProducer()

        # Generator instances
        self._legitimate_generators = [
            CardSwipeGenerator(),
            ATMWithdrawalGenerator(),
            OnlinePurchaseGenerator(),
        ]
        self._fraud_generators = {
            "card_testing": BurstFraudGenerator(),
            "geo_anomaly": GeoAnomalyGenerator(),
            "device_fraud": DeviceMismatchGenerator(),
            "mule_account": MuleAccountGenerator(),
            "atm_fraud": ATMWithdrawalGenerator(),  # Reused with fraud flag override
            "online_fraud": OnlinePurchaseGenerator(),  # Reused with fraud flag override
        }

        # Pools (populated at startup)
        self._customers: list[CustomerProfile] = []
        self._merchants: list[MerchantProfile] = []

        # Precompute fraud type selection
        self._fraud_types = list(self._config.fraud_weights.keys())
        self._fraud_cumulative_weights = self._cumulative(
            [self._config.fraud_weights[ft] for ft in self._fraud_types]
        )

    @staticmethod
    def _cumulative(weights: list[float]) -> list[float]:
        result = []
        total = 0.0
        for w in weights:
            total += w
            result.append(total)
        return result

    def _select_fraud_type(self) -> str:
        """Select a fraud type based on weighted distribution."""
        return random.choices(self._fraud_types, weights=[
            self._config.fraud_weights[ft] for ft in self._fraud_types
        ], k=1)[0]

    def _init_pools(self) -> None:
        """Initialize customer and merchant pools."""
        logger.info("initializing_pools",
                     num_merchants=self._config.num_merchants,
                     num_customers=self._config.num_customers)

        self._merchants = MerchantProfile.generate_pool(self._config.num_merchants)
        merchant_ids = [m.merchant_id for m in self._merchants]
        self._customers = CustomerProfile.generate_pool(self._config.num_customers, merchant_ids)

        logger.info("pools_initialized",
                     merchants=len(self._merchants),
                     customers=len(self._customers))

    def _generate_one(self, now: datetime) -> dict:
        """Generate a single transaction event.

        Returns a serialized dict ready for Kafka.
        """
        customer = random.choice(self._customers)
        merchant = random.choice(self._merchants)
        is_fraud = random.random() < self._config.fraud_ratio

        if is_fraud:
            fraud_type = self._select_fraud_type()
            generator = self._fraud_generators.get(fraud_type, self._fraud_generators["card_testing"])
            txn = generator.generate(customer, merchant, now)
            # Ensure fraud flags are set even for reused legitimate generators
            txn.is_fraud = True
            txn.fraud_type = fraud_type
        else:
            generator = random.choice(self._legitimate_generators)
            txn = generator.generate(customer, merchant, now)

        return txn.to_kafka_dict()

    async def _metrics_reporter(self) -> None:
        """Periodically log throughput metrics."""
        prev_sent = 0
        while not self._shutdown_event.is_set():
            await asyncio.sleep(METRICS_CONFIG.log_interval_seconds)
            metrics = self._producer.get_metrics()
            current_sent = metrics["messages_sent"]
            tps = (current_sent - prev_sent) / METRICS_CONFIG.log_interval_seconds
            prev_sent = current_sent

            logger.info("metrics",
                        tps=round(tps, 1),
                        total_sent=metrics["messages_sent"],
                        total_failed=metrics["messages_failed"],
                        latency_ms=metrics["last_latency_ms"],
                        bytes_sent=metrics["total_bytes_sent"])

    async def run(self) -> None:
        """Main simulation loop."""
        self._init_pools()
        await self._producer.start()

        # Start metrics reporter in background
        metrics_task = asyncio.create_task(self._metrics_reporter())

        interval = 1.0 / self._config.target_tps
        batch: list[dict] = []
        batch_start = time.monotonic()

        logger.info("simulator_started",
                     target_tps=self._config.target_tps,
                     fraud_ratio=self._config.fraud_ratio,
                     topic=KAFKA_CONFIG.topic_raw)

        try:
            while not self._shutdown_event.is_set():
                now = datetime.now(timezone.utc)
                txn = self._generate_one(now)
                batch.append(txn)

                if len(batch) >= self._config.batch_size:
                    await self._producer.send_batch(KAFKA_CONFIG.topic_raw, batch)
                    batch.clear()

                # Rate limiting
                elapsed = time.monotonic() - batch_start
                expected = len(batch) * interval if batch else interval
                if elapsed < expected:
                    await asyncio.sleep(expected - elapsed)
                    batch_start = time.monotonic()

        except asyncio.CancelledError:
            logger.info("simulator_cancelled")
        finally:
            # Flush remaining batch
            if batch:
                await self._producer.send_batch(KAFKA_CONFIG.topic_raw, batch)

            metrics_task.cancel()
            try:
                await metrics_task
            except asyncio.CancelledError:
                pass

            await self._producer.stop()
            logger.info("simulator_stopped", **self._producer.get_metrics())

    def request_shutdown(self) -> None:
        """Signal the simulator to stop gracefully."""
        logger.info("shutdown_requested")
        self._shutdown_event.set()


def main() -> None:
    """Entry point for the transaction simulator."""
    simulator = TransactionSimulator()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, simulator.request_shutdown)

    try:
        loop.run_until_complete(simulator.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
