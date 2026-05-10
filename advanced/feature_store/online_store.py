"""Redis-backed online feature store for real-time model inference."""

from __future__ import annotations

import json
import time
from typing import Optional

import redis
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours


class OnlineFeatureStore:
    """Redis-backed feature store for real-time feature serving.

    Stores and retrieves entity features (keyed by customer_id or
    merchant_id) with automatic TTL-based expiry and freshness tracking.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "features",
        default_ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._default_ttl = default_ttl

    def _key(self, entity_type: str, entity_id: str) -> str:
        return f"{self._prefix}:{entity_type}:{entity_id}"

    def _meta_key(self, entity_type: str, entity_id: str) -> str:
        return f"{self._prefix}:{entity_type}:{entity_id}:_meta"

    def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: dict,
        ttl: Optional[int] = None,
    ) -> None:
        """Store features for an entity.

        Args:
            entity_type: "customer" or "merchant".
            entity_id: Entity identifier.
            features: Dict of feature_name -> value.
            ttl: Time-to-live in seconds (default: 24h).
        """
        key = self._key(entity_type, entity_id)
        meta_key = self._meta_key(entity_type, entity_id)
        ttl = ttl or self._default_ttl

        pipe = self._client.pipeline()
        pipe.hset(key, mapping={k: json.dumps(v) for k, v in features.items()})
        pipe.expire(key, ttl)
        pipe.hset(meta_key, mapping={
            "updated_at": time.time(),
            "feature_count": len(features),
        })
        pipe.expire(meta_key, ttl)
        pipe.execute()

    def get_features(
        self,
        entity_type: str,
        entity_id: str,
        feature_names: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """Retrieve features for an entity.

        Args:
            entity_type: "customer" or "merchant".
            entity_id: Entity identifier.
            feature_names: Specific features to retrieve (None = all).

        Returns:
            Dict of feature values, or None if entity not found.
        """
        key = self._key(entity_type, entity_id)

        if feature_names:
            values = self._client.hmget(key, *feature_names)
            if all(v is None for v in values):
                return None
            return {
                name: json.loads(val) if val is not None else None
                for name, val in zip(feature_names, values)
            }
        else:
            raw = self._client.hgetall(key)
            if not raw:
                return None
            return {k: json.loads(v) for k, v in raw.items()}

    def get_batch(
        self,
        entity_type: str,
        entity_ids: list[str],
        feature_names: Optional[list[str]] = None,
    ) -> dict[str, Optional[dict]]:
        """Batch retrieve features for multiple entities.

        Args:
            entity_type: "customer" or "merchant".
            entity_ids: List of entity identifiers.
            feature_names: Specific features (None = all).

        Returns:
            Dict mapping entity_id to feature dict (or None).
        """
        pipe = self._client.pipeline()
        for eid in entity_ids:
            key = self._key(entity_type, eid)
            if feature_names:
                pipe.hmget(key, *feature_names)
            else:
                pipe.hgetall(key)

        results = pipe.execute()
        output: dict[str, Optional[dict]] = {}

        for eid, raw in zip(entity_ids, results):
            if feature_names:
                if all(v is None for v in raw):
                    output[eid] = None
                else:
                    output[eid] = {
                        name: json.loads(val) if val else None
                        for name, val in zip(feature_names, raw)
                    }
            else:
                output[eid] = {k: json.loads(v) for k, v in raw.items()} if raw else None

        return output

    def get_freshness(self, entity_type: str, entity_id: str) -> Optional[float]:
        """Get feature freshness (seconds since last update).

        Returns:
            Age in seconds, or None if entity not found.
        """
        meta_key = self._meta_key(entity_type, entity_id)
        updated_at = self._client.hget(meta_key, "updated_at")
        if updated_at is None:
            return None
        return time.time() - float(updated_at)

    def delete_features(self, entity_type: str, entity_id: str) -> None:
        """Delete features for an entity."""
        self._client.delete(
            self._key(entity_type, entity_id),
            self._meta_key(entity_type, entity_id),
        )
