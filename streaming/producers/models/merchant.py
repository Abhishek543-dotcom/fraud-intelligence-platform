"""Merchant profile models."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
import uuid

from faker import Faker

_fake = Faker()

# Merchant Category Codes with realistic names
MCC_CATEGORIES: list[tuple[str, str, tuple[float, float]]] = [
    ("5411", "Grocery Stores", (5.0, 300.0)),
    ("5541", "Gas Stations", (10.0, 120.0)),
    ("5812", "Restaurants", (8.0, 250.0)),
    ("5311", "Department Stores", (15.0, 500.0)),
    ("5912", "Pharmacies", (5.0, 200.0)),
    ("5999", "Misc Retail", (10.0, 400.0)),
    ("7011", "Hotels", (50.0, 800.0)),
    ("4511", "Airlines", (100.0, 2000.0)),
    ("5732", "Electronics", (20.0, 3000.0)),
    ("5691", "Clothing Stores", (10.0, 500.0)),
    ("5942", "Book Stores", (5.0, 100.0)),
    ("7832", "Movie Theaters", (8.0, 60.0)),
    ("8011", "Medical Services", (20.0, 1000.0)),
    ("5944", "Jewelry Stores", (25.0, 5000.0)),
    ("5651", "Family Clothing", (15.0, 300.0)),
]

# Major cities with coordinates
CITIES: list[tuple[str, str, float, float]] = [
    ("New York", "US", 40.7128, -74.0060),
    ("Los Angeles", "US", 34.0522, -118.2437),
    ("Chicago", "US", 41.8781, -87.6298),
    ("Houston", "US", 29.7604, -95.3698),
    ("Phoenix", "US", 33.4484, -112.0740),
    ("San Francisco", "US", 37.7749, -122.4194),
    ("Seattle", "US", 47.6062, -122.3321),
    ("Miami", "US", 25.7617, -80.1918),
    ("Denver", "US", 39.7392, -104.9903),
    ("Atlanta", "US", 33.7490, -84.3880),
    ("Boston", "US", 42.3601, -71.0589),
    ("Dallas", "US", 32.7767, -96.7970),
    ("London", "GB", 51.5074, -0.1278),
    ("Paris", "FR", 48.8566, 2.3522),
    ("Tokyo", "JP", 35.6762, 139.6503),
    ("Sydney", "AU", -33.8688, 151.2093),
    ("Toronto", "CA", 43.6532, -79.3832),
    ("Berlin", "DE", 52.5200, 13.4050),
    ("Mumbai", "IN", 19.0760, 72.8777),
    ("São Paulo", "BR", -23.5505, -46.6333),
]


@dataclass
class MerchantProfile:
    """Profile for a simulated merchant."""
    merchant_id: str
    name: str
    category: str  # MCC code
    category_name: str
    city: str
    country: str
    lat: float
    lon: float
    avg_amount_min: float
    avg_amount_max: float
    historical_fraud_rate: float
    is_high_risk: bool

    @staticmethod
    def generate_pool(n: int) -> list[MerchantProfile]:
        """Generate a pool of n merchant profiles."""
        merchants: list[MerchantProfile] = []
        for _ in range(n):
            mcc, cat_name, (amt_min, amt_max) = random.choice(MCC_CATEGORIES)
            city, country, lat, lon = random.choice(CITIES)
            fraud_rate = random.betavariate(1, 50)  # Mostly low, some high
            is_high_risk = fraud_rate > 0.05

            merchants.append(MerchantProfile(
                merchant_id=f"MERCH-{uuid.uuid4().hex[:12].upper()}",
                name=f"{_fake.company()} {cat_name}",
                category=mcc,
                category_name=cat_name,
                city=city,
                country=country,
                lat=lat + random.gauss(0, 0.05),
                lon=lon + random.gauss(0, 0.05),
                avg_amount_min=amt_min,
                avg_amount_max=amt_max,
                historical_fraud_rate=round(fraud_rate, 4),
                is_high_risk=is_high_risk,
            ))
        return merchants
