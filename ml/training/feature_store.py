"""Redis-backed online feature store for fraud detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

try:
    import redis
except ImportError:
    redis = None  # type: ignore[assignment]

from ml.features.feature_definitions import ALL_FEATURE_NAMES

logger = structlog.get_logger(__name__)

DEFAULT_TTL = 86400  # 24 hours
KEY_PREFIX = "fraud:features:"


class FeatureStore:
    """Redis-backed online feature store for real-time fraud scoring.

    Stores per-customer feature vectors with TTL-based expiry.
    """

    def __init__(
        self,
        redis_url: str = "redis://redis:6379/1",
        ttl_seconds: int = DEFAULT_TTL,
        prefix: str = KEY_PREFIX,
    ):
        if redis is None:
            raise ImportError("redis package is required for FeatureStore")

        self.client = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl_seconds
        self.prefix = prefix
        self._version = "v1"

    def _key(self, customer_id: str) -> str:
        """Build Redis key for a customer."""
        return f"{self.prefix}{self._version}:{customer_id}"

    def get_features(self, customer_id: str) -> dict[str, float] | None:
        """Retrieve features for a customer. Returns None if not found."""
        key = self._key(customer_id)
        data = self.client.get(key)
        if data is None:
            logger.debug("feature_miss", customer_id=customer_id)
            return None

        features = json.loads(data)
        logger.debug("feature_hit", customer_id=customer_id)
        return features

    def set_features(self, customer_id: str, features: dict[str, float]) -> None:
        """Store features for a customer with TTL."""
        key = self._key(customer_id)
        payload = {
            **features,
            "_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.setex(key, self.ttl, json.dumps(payload))
        logger.debug("feature_stored", customer_id=customer_id)

    def get_features_batch(self, customer_ids: list[str]) -> dict[str, dict[str, float] | None]:
        """Retrieve features for multiple customers."""
        pipe = self.client.pipeline()
        for cid in customer_ids:
            pipe.get(self._key(cid))

        results = pipe.execute()
        output: dict[str, dict[str, float] | None] = {}
        for cid, data in zip(customer_ids, results):
            output[cid] = json.loads(data) if data else None

        hits = sum(1 for v in output.values() if v is not None)
        logger.info("batch_feature_lookup", total=len(customer_ids), hits=hits)
        return output

    def set_features_batch(self, features_map: dict[str, dict[str, float]]) -> None:
        """Store features for multiple customers."""
        pipe = self.client.pipeline()
        now = datetime.now(timezone.utc).isoformat()

        for cid, features in features_map.items():
            key = self._key(cid)
            payload = {**features, "_updated_at": now}
            pipe.setex(key, self.ttl, json.dumps(payload))

        pipe.execute()
        logger.info("batch_features_stored", count=len(features_map))

    def delete_features(self, customer_id: str) -> None:
        """Remove features for a customer."""
        self.client.delete(self._key(customer_id))

    def get_feature_count(self) -> int:
        """Count customers with stored features."""
        pattern = f"{self.prefix}{self._version}:*"
        count = 0
        for _ in self.client.scan_iter(match=pattern, count=1000):
            count += 1
        return count

    def health_check(self) -> dict[str, Any]:
        """Check feature store health."""
        try:
            self.client.ping()
            return {
                "status": "healthy",
                "version": self._version,
                "ttl_seconds": self.ttl,
                "prefix": self.prefix,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def load_from_dataframe(self, df: Any, customer_id_col: str = "customer_id") -> int:
        """Bulk load features from a pandas DataFrame.

        Used for cold-start population from Iceberg tables.
        """
        import pandas as pd

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Expected a pandas DataFrame")

        feature_cols = [c for c in ALL_FEATURE_NAMES if c in df.columns]
        loaded = 0
        batch: dict[str, dict[str, float]] = {}

        for _, row in df.iterrows():
            cid = str(row[customer_id_col])
            features = {col: float(row[col]) for col in feature_cols}
            batch[cid] = features

            if len(batch) >= 500:
                self.set_features_batch(batch)
                loaded += len(batch)
                batch = {}

        if batch:
            self.set_features_batch(batch)
            loaded += len(batch)

        logger.info("bulk_features_loaded", count=loaded)
        return loaded
