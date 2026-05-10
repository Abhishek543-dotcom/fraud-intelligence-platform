"""Feature computation pipeline for fraud detection."""

from __future__ import annotations

import structlog
import pandas as pd
import numpy as np

from ml.features.feature_definitions import (
    ALL_FEATURE_NAMES,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    FeaturePreprocessor,
    compute_derived_features,
    clip_features,
    fill_missing_features,
    validate_features,
)

logger = structlog.get_logger(__name__)


class FeaturePipeline:
    """End-to-end feature computation pipeline.

    Orchestrates: validation -> derived features -> fill missing -> clip -> scale.
    """

    def __init__(self, scale_numeric: bool = True):
        self.scale_numeric = scale_numeric
        self.preprocessor = FeaturePreprocessor(numeric_features=NUMERIC_FEATURES) if scale_numeric else None
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> FeaturePipeline:
        """Fit pipeline on training data."""
        df = self._prepare(df)
        if self.preprocessor:
            self.preprocessor.fit(df)
        self._fitted = True
        logger.info("feature_pipeline_fitted", rows=len(df), features=len(ALL_FEATURE_NAMES))
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform raw data into model-ready features."""
        df = self._prepare(df)
        if self.preprocessor:
            if not self._fitted:
                raise RuntimeError("Pipeline must be fit before transform")
            df = self.preprocessor.transform(df)
        return df[ALL_FEATURE_NAMES]

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one step."""
        self.fit(df)
        return self.transform(df)

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run validation and basic transforms."""
        issues = validate_features(df)
        if issues:
            logger.warning("feature_validation_issues", issues=issues[:10])

        df = compute_derived_features(df)
        df = fill_missing_features(df)
        df = clip_features(df)
        return df

    def compute_realtime_features(self, transaction: dict) -> dict:
        """Compute features for a single transaction in real-time.

        Used by the streaming scorer and model server.
        """
        df = pd.DataFrame([transaction])
        df = self._prepare(df)
        if self.preprocessor and self._fitted:
            df = self.preprocessor.transform(df)

        return df[ALL_FEATURE_NAMES].iloc[0].to_dict()

    def get_feature_stats(self, df: pd.DataFrame) -> dict:
        """Compute summary statistics for feature monitoring."""
        df = self._prepare(df)
        stats = {}
        for col in ALL_FEATURE_NAMES:
            if col in df.columns:
                series = df[col]
                stats[col] = {
                    "mean": float(series.mean()),
                    "std": float(series.std()),
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "null_pct": float(series.isna().mean()),
                    "p25": float(series.quantile(0.25)),
                    "p50": float(series.quantile(0.50)),
                    "p75": float(series.quantile(0.75)),
                }
        return stats


def generate_synthetic_features(n_samples: int = 10000, fraud_ratio: float = 0.02) -> pd.DataFrame:
    """Generate synthetic feature data for testing and development.

    Produces realistic-looking fraud detection features with the specified
    fraud ratio.
    """
    rng = np.random.default_rng(42)

    n_fraud = int(n_samples * fraud_ratio)
    n_legit = n_samples - n_fraud

    # Legitimate transactions
    legit = pd.DataFrame(
        {
            "tx_count_1h": rng.poisson(2, n_legit),
            "tx_count_24h": rng.poisson(8, n_legit),
            "amount": rng.lognormal(4.0, 1.2, n_legit).clip(0.01, 50000),
            "amount_avg_7d": rng.lognormal(4.0, 0.8, n_legit).clip(0.01, 50000),
            "geo_velocity_kmh": rng.exponential(20, n_legit).clip(0, 200),
            "merchant_risk_score": rng.beta(2, 8, n_legit),
            "device_consistency": rng.choice([0, 1], n_legit, p=[0.05, 0.95]),
            "time_since_last_tx": rng.exponential(7200, n_legit).clip(60, 2592000),
            "is_unusual_hour": rng.choice([0, 1], n_legit, p=[0.9, 0.1]),
            "rapid_tx_count": rng.poisson(0.3, n_legit),
            "is_international": rng.choice([0, 1], n_legit, p=[0.85, 0.15]),
            "card_present": rng.choice([0, 1], n_legit, p=[0.3, 0.7]),
            "is_fraud": 0,
        }
    )

    # Fraudulent transactions (different distributions)
    fraud = pd.DataFrame(
        {
            "tx_count_1h": rng.poisson(8, n_fraud),
            "tx_count_24h": rng.poisson(25, n_fraud),
            "amount": rng.lognormal(6.0, 1.5, n_fraud).clip(0.01, 100000),
            "amount_avg_7d": rng.lognormal(4.0, 0.8, n_fraud).clip(0.01, 50000),
            "geo_velocity_kmh": rng.exponential(500, n_fraud).clip(0, 15000),
            "merchant_risk_score": rng.beta(5, 3, n_fraud),
            "device_consistency": rng.choice([0, 1], n_fraud, p=[0.6, 0.4]),
            "time_since_last_tx": rng.exponential(300, n_fraud).clip(1, 2592000),
            "is_unusual_hour": rng.choice([0, 1], n_fraud, p=[0.4, 0.6]),
            "rapid_tx_count": rng.poisson(4, n_fraud),
            "is_international": rng.choice([0, 1], n_fraud, p=[0.4, 0.6]),
            "card_present": rng.choice([0, 1], n_fraud, p=[0.7, 0.3]),
            "is_fraud": 1,
        }
    )

    df = pd.concat([legit, fraud], ignore_index=True)

    # Compute derived features
    std = df["amount"].std()
    df["amount_zscore"] = (df["amount"] - df["amount_avg_7d"]) / std if std > 0 else 0.0
    avg = df["amount_avg_7d"].replace(0, np.nan)
    df["amount_to_avg_ratio"] = (df["amount"] / avg).fillna(1.0)

    # Shuffle
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    logger.info(
        "synthetic_data_generated",
        total=len(df),
        fraud=n_fraud,
        legit=n_legit,
        fraud_pct=f"{fraud_ratio * 100:.1f}%",
    )
    return df
