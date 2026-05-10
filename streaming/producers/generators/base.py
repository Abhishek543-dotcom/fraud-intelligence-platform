"""Base class for transaction generators."""

from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType


class BaseGenerator(ABC):
    """Abstract base class for all transaction generators.

    Each generator produces transactions of a specific pattern — either
    legitimate or fraudulent — based on customer and merchant profiles.
    """

    @abstractmethod
    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        """Generate a single transaction.

        Args:
            customer: The customer making the transaction.
            merchant: The merchant receiving the transaction.
            timestamp: When the transaction occurs.

        Returns:
            A fully populated Transaction object.
        """

    @staticmethod
    def _random_ip() -> str:
        return f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

    @staticmethod
    def _make_device_fingerprint() -> str:
        return uuid.uuid4().hex[:16]

    @staticmethod
    def _jitter_location(lat: float, lon: float, km_radius: float = 5.0) -> tuple[float, float]:
        """Add random jitter to a location within a given radius in km."""
        # ~0.009 degrees per km at mid-latitudes
        offset = km_radius * 0.009
        return (
            lat + random.gauss(0, offset),
            lon + random.gauss(0, offset),
        )

    @staticmethod
    def _pick_amount(low: float, high: float) -> Decimal:
        """Pick a random amount between low and high as Decimal."""
        return Decimal(str(round(random.uniform(low, high), 2)))
