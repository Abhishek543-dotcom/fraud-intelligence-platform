"""Simulate memory pressure on Spark workers for chaos testing."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


class SparkPressureSimulator:
    """Simulate resource pressure on Spark to test graceful degradation.

    Tests how the platform handles: memory pressure, CPU throttling,
    and OOM conditions on Spark workers.
    """

    def __init__(self, docker_client=None) -> None:
        if docker_client is None:
            import docker
            docker_client = docker.from_env()
        self._docker = docker_client

    async def memory_pressure(
        self,
        container_name: str = "fraud-spark-worker",
        memory_limit_mb: int = 512,
        duration_seconds: int = 60,
    ) -> dict:
        """Reduce Spark worker memory limit to induce pressure.

        Args:
            container_name: Docker container name.
            memory_limit_mb: New memory limit in MB.
            duration_seconds: Duration of the experiment.

        Returns:
            Experiment result dict.
        """
        logger.warning("chaos_spark_memory_pressure",
                        container=container_name,
                        new_limit_mb=memory_limit_mb)

        container = self._docker.containers.get(container_name)
        original_limit = container.attrs["HostConfig"]["Memory"]

        container.update(mem_limit=f"{memory_limit_mb}m")

        await asyncio.sleep(duration_seconds)

        # Restore original limit
        if original_limit > 0:
            container.update(mem_limit=original_limit)
        else:
            container.update(mem_limit=f"1024m")

        logger.info("chaos_spark_memory_restored", container=container_name)

        return {
            "experiment": "spark_memory_pressure",
            "container": container_name,
            "memory_limit_mb": memory_limit_mb,
            "duration_seconds": duration_seconds,
            "status": "completed",
        }

    async def cpu_throttle(
        self,
        container_name: str = "fraud-spark-worker",
        cpu_quota: int = 50000,
        duration_seconds: int = 60,
    ) -> dict:
        """Throttle Spark worker CPU.

        Args:
            container_name: Docker container name.
            cpu_quota: CPU quota in microseconds per period (50000 = 50%).
            duration_seconds: Duration of the experiment.

        Returns:
            Experiment result dict.
        """
        logger.warning("chaos_spark_cpu_throttle",
                        container=container_name,
                        cpu_quota=cpu_quota)

        container = self._docker.containers.get(container_name)
        container.update(cpu_quota=cpu_quota)

        await asyncio.sleep(duration_seconds)

        container.update(cpu_quota=-1)  # Remove limit
        logger.info("chaos_spark_cpu_restored")

        return {
            "experiment": "spark_cpu_throttle",
            "container": container_name,
            "cpu_quota": cpu_quota,
            "duration_seconds": duration_seconds,
            "status": "completed",
        }
