"""Customer profile models with behavioral history."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from faker import Faker

from .merchant import CITIES

_fake = Faker()


def _random_ip() -> str:
    return f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _random_device() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class CustomerProfile:
    """Profile for a simulated customer."""
    customer_id: str
    name: str
    home_city: str
    home_country: str
    home_lat: float
    home_lon: float
    typical_spend_min: float
    typical_spend_max: float
    usual_merchant_ids: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    usual_ips: list[str] = field(default_factory=list)
    active_hours_start: int = 8   # 8 AM
    active_hours_end: int = 23    # 11 PM
    risk_score: float = 0.0

    def is_typical_amount(self, amount: float) -> bool:
        """Check if an amount is within the customer's typical range."""
        return self.typical_spend_min <= amount <= self.typical_spend_max

    @staticmethod
    def generate_pool(n: int, merchant_ids: list[str]) -> list[CustomerProfile]:
        """Generate a pool of n customer profiles.

        Args:
            n: Number of customer profiles to generate.
            merchant_ids: Pool of merchant IDs to assign as usual merchants.

        Returns:
            List of generated customer profiles.
        """
        customers: list[CustomerProfile] = []
        for _ in range(n):
            city, country, lat, lon = random.choice(CITIES)
            spend_base = random.lognormvariate(4.0, 1.0)  # Median ~$55
            spend_min = max(5.0, spend_base * 0.1)
            spend_max = spend_base * 3.0

            # Each customer has 3-10 usual merchants
            num_usual = random.randint(3, 10)
            usual = random.sample(merchant_ids, min(num_usual, len(merchant_ids)))

            # 1-3 devices per customer
            devices = [_random_device() for _ in range(random.randint(1, 3))]

            # 1-2 usual IPs
            ips = [_random_ip() for _ in range(random.randint(1, 2))]

            customers.append(CustomerProfile(
                customer_id=f"CUST-{uuid.uuid4().hex[:12].upper()}",
                name=_fake.name(),
                home_city=city,
                home_country=country,
                home_lat=lat + random.gauss(0, 0.02),
                home_lon=lon + random.gauss(0, 0.02),
                typical_spend_min=round(spend_min, 2),
                typical_spend_max=round(spend_max, 2),
                usual_merchant_ids=usual,
                devices=devices,
                usual_ips=ips,
                active_hours_start=random.randint(6, 10),
                active_hours_end=random.randint(20, 23),
                risk_score=random.betavariate(1, 20),
            ))
        return customers
