import json
from typing import Any

import structlog

logger = structlog.get_logger()

DEFAULT_TTL = 300  # 5 minutes


class CacheService:
    """Redis-backed caching service."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get(self, key: str) -> Any | None:
        """Get cached value."""
        raw = await self.redis.get(f"cache:{key}")
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        """Set cached value with TTL."""
        await self.redis.setex(f"cache:{key}", ttl, json.dumps(value))

    async def delete(self, key: str) -> None:
        """Delete cached value."""
        await self.redis.delete(f"cache:{key}")

    async def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate all keys matching pattern."""
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=f"cache:{pattern}", count=100)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break
