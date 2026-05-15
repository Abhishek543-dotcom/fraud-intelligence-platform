"""FastAPI inference service for real-time fraud scoring."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import structlog
import yaml
from fastapi import FastAPI, HTTPException
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from pydantic import BaseModel, Field
from starlette.responses import Response

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = Path(__file__).resolve().parents[1]
# Support both layouts: project root with ml/ subdir, and ml/ mounted as cwd
CONFIG_PATH = ML_ROOT / "config.yml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = PROJECT_ROOT / "ml" / "config.yml"
MODELS_DIR = ML_ROOT / "models"
if not MODELS_DIR.exists():
    MODELS_DIR = PROJECT_ROOT / "ml" / "models"

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
PREDICTION_COUNT = Counter(
    "fraud_predictions_total", "Total predictions made", ["risk_level"]
)
PREDICTION_LATENCY = Histogram(
    "fraud_prediction_duration_seconds",
    "Prediction latency in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)
MODEL_LOADED = Gauge("fraud_model_loaded", "Whether a model is loaded", ["model_name"])
FRAUD_RATIO = Gauge("fraud_prediction_fraud_ratio", "Rolling fraud prediction ratio")

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TransactionFeatures(BaseModel):
    """Input features for a single transaction."""

    tx_count_1h: float = 0
    tx_count_24h: float = 0
    amount: float = 0.0
    amount_avg_7d: float = 0.0
    amount_zscore: float = 0.0
    geo_velocity_kmh: float = 0.0
    merchant_risk_score: float = 0.0
    device_consistency: float = 0.0
    time_since_last_tx: float = 0.0
    is_unusual_hour: float = 0
    rapid_tx_count: float = 0
    is_international: float = 0
    card_present: float = 0
    amount_to_avg_ratio: float = 0.0


class PredictionResponse(BaseModel):
    """Prediction result."""

    fraud_probability: float
    risk_level: str
    model_version: str
    latency_ms: float
    timestamp: str


class BatchRequest(BaseModel):
    """Batch prediction request."""

    transactions: list[TransactionFeatures]


class BatchResponse(BaseModel):
    """Batch prediction result."""

    predictions: list[PredictionResponse]
    total_latency_ms: float
    count: int


class ModelInfo(BaseModel):
    """Current model information."""

    model_type: str
    version: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Model Manager
# ---------------------------------------------------------------------------

class ModelManager:
    """Manages model loading and prediction."""

    def __init__(self):
        self.config: dict = {}
        self.model: Any = None
        self.model_type: str = ""
        self.model_version: str = ""
        self.scaler: Any = None
        self.norm_params: dict = {}
        self.thresholds: dict = {}
        self.ensemble_config: dict = {}
        self._total_predictions: int = 0
        self._fraud_predictions: int = 0

    def load(self) -> None:
        """Load model based on config."""
        with open(CONFIG_PATH) as f:
            self.config = yaml.safe_load(f)

        self.thresholds = self.config.get("thresholds", {"block": 0.85, "review": 0.60, "alert": 0.40})
        self.model_type = self.config.get("inference", {}).get("model_type", "ensemble")

        # Try to find latest model version
        self.model_version = self._find_latest_version()

        if self.model_type == "ensemble":
            self._load_ensemble()
        elif self.model_type == "xgboost":
            self._load_xgboost()
        elif self.model_type == "random_forest":
            self._load_random_forest()
        elif self.model_type == "isolation_forest":
            self._load_isolation_forest()
        else:
            logger.warning("unknown_model_type", model_type=self.model_type)

    def _find_latest_version(self) -> str:
        """Find the latest model version from saved files."""
        pattern = f"{self.model_type}_v*.json" if self.model_type == "xgboost" else f"{self.model_type}_v*.joblib"
        if self.model_type == "ensemble":
            pattern = "ensemble_v*.json"

        files = list(MODELS_DIR.glob(pattern))
        if not files:
            return "unknown"

        latest = sorted(files)[-1]
        # Extract version from filename
        stem = latest.stem
        if "_v" in stem:
            return stem.split("_v", 1)[1]
        return "unknown"

    def _load_ensemble(self) -> None:
        """Load ensemble configuration and all sub-models."""
        ensemble_path = MODELS_DIR / f"ensemble_v{self.model_version}.json"
        if not ensemble_path.exists():
            logger.warning("ensemble_not_found", path=str(ensemble_path))
            return

        with open(ensemble_path) as f:
            self.ensemble_config = json.load(f)

        # Load sub-models
        self._models = {}
        v = self.model_version

        try:
            from xgboost import XGBClassifier

            xgb = XGBClassifier()
            xgb.load_model(str(MODELS_DIR / f"xgboost_v{v}.json"))
            self._models["xgboost"] = xgb
        except Exception as e:
            logger.warning("xgboost_load_failed", error=str(e))

        try:
            self._models["random_forest"] = joblib.load(MODELS_DIR / f"random_forest_v{v}.joblib")
        except Exception as e:
            logger.warning("random_forest_load_failed", error=str(e))

        try:
            self._models["isolation_forest"] = joblib.load(MODELS_DIR / f"isolation_forest_v{v}.joblib")
            self.scaler = joblib.load(MODELS_DIR / f"isolation_forest_scaler_v{v}.joblib")
            with open(MODELS_DIR / f"isolation_forest_norm_v{v}.json") as f:
                self.norm_params = json.load(f)
        except Exception as e:
            logger.warning("isolation_forest_load_failed", error=str(e))

        MODEL_LOADED.labels(model_name="ensemble").set(1)
        logger.info("ensemble_loaded", version=v, sub_models=list(self._models.keys()))

    def _load_xgboost(self) -> None:
        from xgboost import XGBClassifier

        model_path = MODELS_DIR / f"xgboost_v{self.model_version}.json"
        if model_path.exists():
            self.model = XGBClassifier()
            self.model.load_model(str(model_path))
            MODEL_LOADED.labels(model_name="xgboost").set(1)
            logger.info("xgboost_loaded", version=self.model_version)

    def _load_random_forest(self) -> None:
        model_path = MODELS_DIR / f"random_forest_v{self.model_version}.joblib"
        if model_path.exists():
            self.model = joblib.load(model_path)
            MODEL_LOADED.labels(model_name="random_forest").set(1)
            logger.info("random_forest_loaded", version=self.model_version)

    def _load_isolation_forest(self) -> None:
        model_path = MODELS_DIR / f"isolation_forest_v{self.model_version}.joblib"
        if model_path.exists():
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(MODELS_DIR / f"isolation_forest_scaler_v{self.model_version}.joblib")
            with open(MODELS_DIR / f"isolation_forest_norm_v{self.model_version}.json") as f:
                self.norm_params = json.load(f)
            MODEL_LOADED.labels(model_name="isolation_forest").set(1)
            logger.info("isolation_forest_loaded", version=self.model_version)

    def predict(self, features: dict[str, float]) -> float:
        """Predict fraud probability for a single transaction."""
        import pandas as pd

        feature_names = [
            "tx_count_1h", "tx_count_24h", "amount", "amount_avg_7d",
            "amount_zscore", "geo_velocity_kmh", "merchant_risk_score",
            "device_consistency", "time_since_last_tx", "is_unusual_hour",
            "rapid_tx_count", "is_international", "card_present", "amount_to_avg_ratio",
        ]
        X = pd.DataFrame([{k: features.get(k, 0.0) for k in feature_names}])

        if self.model_type == "ensemble" and hasattr(self, "_models"):
            return self._predict_ensemble(X)
        elif self.model is not None:
            if self.model_type == "isolation_forest":
                return self._predict_isolation_forest(X)
            else:
                return float(self.model.predict_proba(X)[:, 1][0])

        # Fallback: rule-based scoring
        return self._rule_based_score(features)

    def _predict_ensemble(self, X) -> float:
        """Predict using weighted ensemble."""
        from ml.features.feature_definitions import NUMERIC_FEATURES

        weights = self.ensemble_config.get("weights", {"xgboost": 0.5, "random_forest": 0.3, "isolation_forest": 0.2})
        total = 0.0

        if "xgboost" in self._models:
            total += weights.get("xgboost", 0) * float(self._models["xgboost"].predict_proba(X)[:, 1][0])

        if "random_forest" in self._models:
            total += weights.get("random_forest", 0) * float(self._models["random_forest"].predict_proba(X)[:, 1][0])

        if "isolation_forest" in self._models:
            X_scaled = self.scaler.transform(X[NUMERIC_FEATURES])
            raw = self._models["isolation_forest"].decision_function(X_scaled)[0]
            min_s, max_s = self.norm_params["min_score"], self.norm_params["max_score"]
            r = max_s - min_s
            prob = 1.0 - (raw - min_s) / r if r > 0 else 0.0
            total += weights.get("isolation_forest", 0) * prob

        return float(np.clip(total, 0.0, 1.0))

    def _predict_isolation_forest(self, X) -> float:
        from ml.features.feature_definitions import NUMERIC_FEATURES

        X_scaled = self.scaler.transform(X[NUMERIC_FEATURES])
        raw = self.model.decision_function(X_scaled)[0]
        min_s, max_s = self.norm_params["min_score"], self.norm_params["max_score"]
        r = max_s - min_s
        return float(1.0 - (raw - min_s) / r) if r > 0 else 0.0

    def _rule_based_score(self, features: dict[str, float]) -> float:
        """Fallback rule-based scoring when no model is available."""
        score = 0.0
        if features.get("amount_zscore", 0) > 3.0:
            score += 0.3
        if features.get("geo_velocity_kmh", 0) > 500:
            score += 0.25
        if features.get("device_consistency", 1) == 0:
            score += 0.15
        if features.get("rapid_tx_count", 0) > 5:
            score += 0.15
        if features.get("is_unusual_hour", 0) == 1:
            score += 0.1
        if features.get("merchant_risk_score", 0) > 0.7:
            score += 0.15
        return min(score, 1.0)

    def get_risk_level(self, probability: float) -> str:
        """Map probability to risk level."""
        if probability >= self.thresholds.get("block", 0.85):
            return "HIGH"
        elif probability >= self.thresholds.get("review", 0.60):
            return "MEDIUM"
        elif probability >= self.thresholds.get("alert", 0.40):
            return "LOW"
        return "NONE"

    def update_stats(self, is_fraud: bool) -> None:
        """Update running prediction statistics."""
        self._total_predictions += 1
        if is_fraud:
            self._fraud_predictions += 1
        if self._total_predictions > 0:
            FRAUD_RATIO.set(self._fraud_predictions / self._total_predictions)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

manager = ModelManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    try:
        manager.load()
        logger.info("model_server_started", model_type=manager.model_type, version=manager.model_version)
    except Exception as e:
        logger.error("model_load_failed", error=str(e))
    yield
    logger.info("model_server_shutting_down")


app = FastAPI(
    title="Fraud Detection Model Server",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": manager.model is not None or hasattr(manager, "_models")}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/model/info", response_model=ModelInfo)
async def model_info():
    return ModelInfo(
        model_type=manager.model_type,
        version=manager.model_version,
        status="active" if (manager.model is not None or hasattr(manager, "_models")) else "not_loaded",
        metrics=manager.ensemble_config.get("metrics", {}),
    )


@app.post("/model/reload")
async def reload_model():
    """Hot-reload model from disk."""
    try:
        manager.load()
        return {"status": "reloaded", "model_type": manager.model_type, "version": manager.model_version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict", response_model=PredictionResponse)
async def predict(transaction: TransactionFeatures):
    """Score a single transaction."""
    start = time.perf_counter()

    features = transaction.model_dump()
    probability = manager.predict(features)
    risk_level = manager.get_risk_level(probability)

    elapsed_ms = (time.perf_counter() - start) * 1000

    PREDICTION_COUNT.labels(risk_level=risk_level).inc()
    PREDICTION_LATENCY.observe(elapsed_ms / 1000)
    manager.update_stats(risk_level in ("HIGH", "MEDIUM"))

    return PredictionResponse(
        fraud_probability=round(probability, 6),
        risk_level=risk_level,
        model_version=manager.model_version,
        latency_ms=round(elapsed_ms, 3),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/predict/batch", response_model=BatchResponse)
async def predict_batch(request: BatchRequest):
    """Score a batch of transactions."""
    start = time.perf_counter()
    predictions = []

    for tx in request.transactions:
        tx_start = time.perf_counter()
        features = tx.model_dump()
        probability = manager.predict(features)
        risk_level = manager.get_risk_level(probability)
        tx_elapsed = (time.perf_counter() - tx_start) * 1000

        PREDICTION_COUNT.labels(risk_level=risk_level).inc()
        manager.update_stats(risk_level in ("HIGH", "MEDIUM"))

        predictions.append(
            PredictionResponse(
                fraud_probability=round(probability, 6),
                risk_level=risk_level,
                model_version=manager.model_version,
                latency_ms=round(tx_elapsed, 3),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    total_elapsed = (time.perf_counter() - start) * 1000
    PREDICTION_LATENCY.observe(total_elapsed / 1000)

    return BatchResponse(
        predictions=predictions,
        total_latency_ms=round(total_elapsed, 3),
        count=len(predictions),
    )
