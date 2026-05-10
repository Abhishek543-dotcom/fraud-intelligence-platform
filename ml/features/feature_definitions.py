"""Feature definitions and transformations for fraud detection models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


class FeatureType(str, Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BINARY = "binary"


@dataclass
class FeatureDefinition:
    """Specification for a single feature."""

    name: str
    feature_type: FeatureType
    description: str
    min_value: float | None = None
    max_value: float | None = None
    default_value: float = 0.0
    is_derived: bool = False
    source_features: list[str] = field(default_factory=list)


# Complete feature catalog
FEATURE_CATALOG: dict[str, FeatureDefinition] = {
    "tx_count_1h": FeatureDefinition(
        name="tx_count_1h",
        feature_type=FeatureType.NUMERIC,
        description="Number of transactions by customer in last 1 hour",
        min_value=0,
        max_value=100,
    ),
    "tx_count_24h": FeatureDefinition(
        name="tx_count_24h",
        feature_type=FeatureType.NUMERIC,
        description="Number of transactions by customer in last 24 hours",
        min_value=0,
        max_value=500,
    ),
    "amount": FeatureDefinition(
        name="amount",
        feature_type=FeatureType.NUMERIC,
        description="Transaction amount in USD",
        min_value=0.01,
        max_value=100000.0,
    ),
    "amount_avg_7d": FeatureDefinition(
        name="amount_avg_7d",
        feature_type=FeatureType.NUMERIC,
        description="Average transaction amount over last 7 days",
        min_value=0.0,
        max_value=100000.0,
    ),
    "amount_zscore": FeatureDefinition(
        name="amount_zscore",
        feature_type=FeatureType.NUMERIC,
        description="Z-score of amount relative to customer average",
        min_value=-10.0,
        max_value=10.0,
        is_derived=True,
        source_features=["amount", "amount_avg_7d"],
    ),
    "geo_velocity_kmh": FeatureDefinition(
        name="geo_velocity_kmh",
        feature_type=FeatureType.NUMERIC,
        description="Velocity between this and last transaction location (km/h)",
        min_value=0.0,
        max_value=15000.0,
    ),
    "merchant_risk_score": FeatureDefinition(
        name="merchant_risk_score",
        feature_type=FeatureType.NUMERIC,
        description="Risk score assigned to the merchant (0.0-1.0)",
        min_value=0.0,
        max_value=1.0,
    ),
    "device_consistency": FeatureDefinition(
        name="device_consistency",
        feature_type=FeatureType.BINARY,
        description="Whether device fingerprint matches known customer devices",
        min_value=0,
        max_value=1,
    ),
    "time_since_last_tx": FeatureDefinition(
        name="time_since_last_tx",
        feature_type=FeatureType.NUMERIC,
        description="Seconds since customer's last transaction",
        min_value=0.0,
        max_value=2592000.0,  # 30 days
    ),
    "is_unusual_hour": FeatureDefinition(
        name="is_unusual_hour",
        feature_type=FeatureType.BINARY,
        description="Whether transaction occurred during unusual hours (00:00-06:00)",
        min_value=0,
        max_value=1,
    ),
    "rapid_tx_count": FeatureDefinition(
        name="rapid_tx_count",
        feature_type=FeatureType.NUMERIC,
        description="Number of transactions within 5-minute window",
        min_value=0,
        max_value=50,
    ),
    "is_international": FeatureDefinition(
        name="is_international",
        feature_type=FeatureType.BINARY,
        description="Whether transaction is cross-border",
        min_value=0,
        max_value=1,
    ),
    "card_present": FeatureDefinition(
        name="card_present",
        feature_type=FeatureType.BINARY,
        description="Whether physical card was present at POS",
        min_value=0,
        max_value=1,
    ),
    "amount_to_avg_ratio": FeatureDefinition(
        name="amount_to_avg_ratio",
        feature_type=FeatureType.NUMERIC,
        description="Ratio of current amount to 7-day average",
        min_value=0.0,
        max_value=1000.0,
        is_derived=True,
        source_features=["amount", "amount_avg_7d"],
    ),
}

ALL_FEATURE_NAMES = list(FEATURE_CATALOG.keys())
NUMERIC_FEATURES = [f.name for f in FEATURE_CATALOG.values() if f.feature_type == FeatureType.NUMERIC]
CATEGORICAL_FEATURES = [
    f.name
    for f in FEATURE_CATALOG.values()
    if f.feature_type in (FeatureType.CATEGORICAL, FeatureType.BINARY)
]


def validate_features(df: pd.DataFrame) -> list[str]:
    """Validate feature DataFrame against definitions. Returns list of issues."""
    issues: list[str] = []
    for name, defn in FEATURE_CATALOG.items():
        if name not in df.columns:
            issues.append(f"Missing feature: {name}")
            continue

        col = df[name]
        null_count = col.isna().sum()
        if null_count > 0:
            issues.append(f"{name}: {null_count} null values")

        if defn.min_value is not None:
            below = (col < defn.min_value).sum()
            if below > 0:
                issues.append(f"{name}: {below} values below min ({defn.min_value})")

        if defn.max_value is not None:
            above = (col > defn.max_value).sum()
            if above > 0:
                issues.append(f"{name}: {above} values above max ({defn.max_value})")

    return issues


def compute_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived features from base features."""
    df = df.copy()

    if "amount" in df.columns and "amount_avg_7d" in df.columns:
        std = df["amount"].std()
        if std > 0:
            df["amount_zscore"] = (df["amount"] - df["amount_avg_7d"]) / std
        else:
            df["amount_zscore"] = 0.0

        avg = df["amount_avg_7d"].replace(0, np.nan)
        df["amount_to_avg_ratio"] = (df["amount"] / avg).fillna(1.0)

    return df


def clip_features(df: pd.DataFrame) -> pd.DataFrame:
    """Clip feature values to their defined ranges."""
    df = df.copy()
    for name, defn in FEATURE_CATALOG.items():
        if name in df.columns:
            if defn.min_value is not None and defn.max_value is not None:
                df[name] = df[name].clip(lower=defn.min_value, upper=defn.max_value)
    return df


def fill_missing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing features with defaults from catalog."""
    df = df.copy()
    for name, defn in FEATURE_CATALOG.items():
        if name in df.columns:
            df[name] = df[name].fillna(defn.default_value)
        else:
            df[name] = defn.default_value
    return df


class FeaturePreprocessor:
    """Preprocessor that scales numeric features using StandardScaler."""

    def __init__(self, numeric_features: list[str] | None = None):
        self.numeric_features = numeric_features or NUMERIC_FEATURES
        self.scaler = StandardScaler()
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> FeaturePreprocessor:
        """Fit the scaler on training data."""
        self.scaler.fit(df[self.numeric_features])
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform features: scale numerics, pass through categoricals."""
        if not self._fitted:
            raise RuntimeError("Preprocessor must be fit before transform")

        result = df.copy()
        result[self.numeric_features] = self.scaler.transform(df[self.numeric_features])
        return result

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one step."""
        self.fit(df)
        return self.transform(df)

    def get_params(self) -> dict[str, Any]:
        """Return scaler parameters for serialization."""
        if not self._fitted:
            return {}
        return {
            "mean": self.scaler.mean_.tolist(),
            "scale": self.scaler.scale_.tolist(),
            "numeric_features": self.numeric_features,
        }
