"""Self-healing supervisor for Spark streaming jobs."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class JobState:
    """Tracks the state of a supervised streaming job."""
    name: str
    start_fn: Callable
    restarts: int = 0
    last_restart: float = 0.0
    is_running: bool = False
    last_error: Optional[str] = None
    restart_timestamps: list[float] = field(default_factory=list)


class StreamingSupervisor:
    """Monitor and auto-restart failed Spark streaming queries.

    Features:
        - Detect stopped/failed queries
        - Auto-restart with exponential backoff
        - Alert on repeated failures (>3 in 10 minutes)
        - Health endpoint for monitoring
    """

    MAX_RESTARTS_WINDOW = 3
    WINDOW_SECONDS = 600  # 10 minutes
    BASE_BACKOFF_SECONDS = 5.0
    MAX_BACKOFF_SECONDS = 120.0

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._running = False
        self._alert_callback: Optional[Callable] = None

    def register_job(self, name: str, start_fn: Callable) -> None:
        """Register a streaming job to supervise.

        Args:
            name: Unique name for the job.
            start_fn: Async callable that starts the streaming query.
        """
        self._jobs[name] = JobState(name=name, start_fn=start_fn)
        logger.info("job_registered", name=name)

    def set_alert_callback(self, callback: Callable) -> None:
        """Set a callback function for alerting on repeated failures.

        Args:
            callback: Async callable(job_name, restart_count, error).
        """
        self._alert_callback = callback

    async def start(self) -> None:
        """Start supervising all registered jobs."""
        self._running = True
        logger.info("supervisor_started", jobs=list(self._jobs.keys()))

        # Start all jobs
        for name, job in self._jobs.items():
            await self._start_job(job)

        # Monitor loop
        while self._running:
            for name, job in self._jobs.items():
                if not job.is_running:
                    await self._handle_failure(job)
            await asyncio.sleep(5.0)

    async def stop(self) -> None:
        """Stop the supervisor."""
        self._running = False
        logger.info("supervisor_stopped")

    async def _start_job(self, job: JobState) -> None:
        """Start a streaming job."""
        try:
            await job.start_fn()
            job.is_running = True
            job.last_error = None
            logger.info("job_started", name=job.name)
        except Exception as exc:
            job.is_running = False
            job.last_error = str(exc)
            logger.error("job_start_failed", name=job.name, error=str(exc))

    async def _handle_failure(self, job: JobState) -> None:
        """Handle a failed job: restart with backoff or alert."""
        now = time.time()

        # Clean old restart timestamps
        job.restart_timestamps = [
            ts for ts in job.restart_timestamps
            if now - ts < self.WINDOW_SECONDS
        ]

        # Check if too many restarts
        if len(job.restart_timestamps) >= self.MAX_RESTARTS_WINDOW:
            logger.critical("job_restart_limit_exceeded",
                            name=job.name,
                            restarts_in_window=len(job.restart_timestamps))

            if self._alert_callback:
                await self._alert_callback(
                    job.name,
                    len(job.restart_timestamps),
                    job.last_error or "Unknown error",
                )
            return

        # Exponential backoff
        backoff = min(
            self.BASE_BACKOFF_SECONDS * (2 ** len(job.restart_timestamps)),
            self.MAX_BACKOFF_SECONDS,
        )

        logger.warning("job_restarting",
                        name=job.name,
                        attempt=len(job.restart_timestamps) + 1,
                        backoff_seconds=backoff,
                        last_error=job.last_error)

        await asyncio.sleep(backoff)

        job.restart_timestamps.append(now)
        job.restarts += 1
        job.last_restart = now

        await self._start_job(job)

    def health(self) -> dict:
        """Return health status of all supervised jobs."""
        return {
            "supervisor_running": self._running,
            "jobs": {
                name: {
                    "is_running": job.is_running,
                    "restarts": job.restarts,
                    "last_error": job.last_error,
                    "recent_restarts": len([
                        ts for ts in job.restart_timestamps
                        if time.time() - ts < self.WINDOW_SECONDS
                    ]),
                }
                for name, job in self._jobs.items()
            },
        }
