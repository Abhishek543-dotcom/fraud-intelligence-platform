"""Simulate Kafka broker failures for chaos testing."""

from __future__ import annotations

import asyncio
import random

import structlog

logger = structlog.get_logger(__name__)


class KafkaFailureSimulator:
    """Simulate Kafka failures to test system resilience.

    Provides controlled chaos experiments: pause Kafka container,
    kill broker process, introduce network partition, and inject
    message production errors.
    """

    def __init__(self, docker_client=None) -> None:
        """Initialize with an optional Docker client.

        Args:
            docker_client: A docker.DockerClient instance.
                If None, will import and create one.
        """
        if docker_client is None:
            import docker
            docker_client = docker.from_env()
        self._docker = docker_client

    async def pause_broker(self, container_name: str = "fraud-kafka", duration_seconds: int = 30) -> dict:
        """Pause the Kafka container to simulate broker freeze.

        Args:
            container_name: Docker container name.
            duration_seconds: How long to keep the broker paused.

        Returns:
            Experiment result dict.
        """
        logger.warning("chaos_kafka_pause", container=container_name, duration=duration_seconds)

        container = self._docker.containers.get(container_name)
        container.pause()

        await asyncio.sleep(duration_seconds)

        container.unpause()
        logger.info("chaos_kafka_resumed", container=container_name)

        return {
            "experiment": "kafka_pause",
            "container": container_name,
            "duration_seconds": duration_seconds,
            "status": "completed",
        }

    async def kill_and_restart(self, container_name: str = "fraud-kafka", downtime_seconds: int = 10) -> dict:
        """Kill and restart the Kafka broker.

        Args:
            container_name: Docker container name.
            downtime_seconds: Seconds before restart.

        Returns:
            Experiment result dict.
        """
        logger.warning("chaos_kafka_kill", container=container_name)

        container = self._docker.containers.get(container_name)
        container.kill()

        await asyncio.sleep(downtime_seconds)

        container.start()
        logger.info("chaos_kafka_restarted", container=container_name)

        return {
            "experiment": "kafka_kill_restart",
            "container": container_name,
            "downtime_seconds": downtime_seconds,
            "status": "completed",
        }

    async def simulate_slow_broker(self, container_name: str = "fraud-kafka", delay_ms: int = 500, duration_seconds: int = 60) -> dict:
        """Add network latency to Kafka container using tc.

        Args:
            container_name: Docker container name.
            delay_ms: Artificial delay in milliseconds.
            duration_seconds: How long to apply the delay.

        Returns:
            Experiment result dict.
        """
        logger.warning("chaos_kafka_slow", delay_ms=delay_ms, duration=duration_seconds)

        container = self._docker.containers.get(container_name)
        container.exec_run(f"tc qdisc add dev eth0 root netem delay {delay_ms}ms", privileged=True)

        await asyncio.sleep(duration_seconds)

        container.exec_run("tc qdisc del dev eth0 root", privileged=True)
        logger.info("chaos_kafka_slow_removed")

        return {
            "experiment": "kafka_slow_broker",
            "delay_ms": delay_ms,
            "duration_seconds": duration_seconds,
            "status": "completed",
        }
