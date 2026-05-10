"""Geo-anomaly (impossible travel) fraud generator."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile, CITIES
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in km between two points using the haversine formula."""
    R = 6371.0  # Earth radius in km
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


class GeoAnomalyGenerator(BaseGenerator):
    """Generates impossible-travel fraud transactions.

    Simulates a transaction from a location >500km away from the
    customer's home city, as if the card was used in two distant
    places within an impossibly short time window.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        # Find a city far from the customer's home
        far_city = self._pick_distant_city(customer.home_lat, customer.home_lon)
        far_name, far_country, far_lat, far_lon = far_city
        distance_km = haversine_km(customer.home_lat, customer.home_lon, far_lat, far_lon)

        amount = self._pick_amount(50.0, 2000.0)
        device = random.choice(customer.devices) if customer.devices else self._make_device_fingerprint()

        return Transaction(
            customer_id=customer.customer_id,
            merchant_id=merchant.merchant_id,
            amount=amount,
            currency="USD",
            transaction_type=TransactionType.CARD_SWIPE,
            timestamp=timestamp,
            merchant_category=merchant.category,
            merchant_name=merchant.name,
            merchant_country=far_country,
            merchant_city=far_name,
            customer_lat=far_lat + random.gauss(0, 0.01),
            customer_lon=far_lon + random.gauss(0, 0.01),
            device_id=device,
            device_fingerprint=device,
            ip_address=self._random_ip(),
            channel=Channel.POS,
            is_international=far_country != customer.home_country,
            card_present=True,
            authentication_method=random.choice([AuthMethod.CHIP, AuthMethod.SWIPE]),
            risk_indicators={
                "impossible_travel": True,
                "distance_km": round(distance_km, 1),
                "home_city": customer.home_city,
                "transaction_city": far_name,
            },
            metadata={"generator": "geo_anomaly", "distance_km": round(distance_km, 1)},
            is_fraud=True,
            fraud_type="geo_anomaly",
        )

    @staticmethod
    def _pick_distant_city(lat: float, lon: float, min_distance_km: float = 500.0) -> tuple[str, str, float, float]:
        """Pick a random city at least min_distance_km away."""
        candidates = [
            (name, country, clat, clon)
            for name, country, clat, clon in CITIES
            if haversine_km(lat, lon, clat, clon) > min_distance_km
        ]
        if not candidates:
            # Fallback: pick any different city
            candidates = [(name, country, clat, clon) for name, country, clat, clon in CITIES
                          if abs(clat - lat) > 1 or abs(clon - lon) > 1]
        return random.choice(candidates) if candidates else CITIES[0]
