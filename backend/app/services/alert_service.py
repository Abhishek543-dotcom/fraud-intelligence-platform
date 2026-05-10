import json
import structlog
from datetime import datetime

logger = structlog.get_logger()


class AlertService:
    """Business logic for fraud alert management."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self._recent_alerts_key = "recent_alerts"
        self._max_recent = 1000

    async def store_alert(self, alert: dict) -> None:
        """Store alert in Redis for quick retrieval."""
        alert_json = json.dumps(alert)
        await self.redis.lpush(self._recent_alerts_key, alert_json)
        await self.redis.ltrim(self._recent_alerts_key, 0, self._max_recent - 1)

        # Index by severity for fast filtering
        severity = alert.get("severity", "unknown")
        await self.redis.sadd(f"alerts:severity:{severity}", alert.get("alert_id", ""))

        # Index by status
        status = alert.get("status", "open")
        await self.redis.sadd(f"alerts:status:{status}", alert.get("alert_id", ""))

    async def get_recent_alerts(self, count: int = 100) -> list[dict]:
        """Get recent alerts from Redis."""
        raw = await self.redis.lrange(self._recent_alerts_key, 0, count - 1)
        return [json.loads(r) for r in raw]

    async def update_status(self, alert_id: str, old_status: str, new_status: str) -> None:
        """Update alert status in Redis indices."""
        await self.redis.srem(f"alerts:status:{old_status}", alert_id)
        await self.redis.sadd(f"alerts:status:{new_status}", alert_id)

    async def get_stats(self) -> dict:
        """Get alert statistics from Redis."""
        stats = {}
        for status in ["open", "investigating", "resolved", "false_positive"]:
            count = await self.redis.scard(f"alerts:status:{status}")
            stats[status] = count
        for severity in ["critical", "high", "medium", "low"]:
            count = await self.redis.scard(f"alerts:severity:{severity}")
            stats[f"severity_{severity}"] = count
        return stats
