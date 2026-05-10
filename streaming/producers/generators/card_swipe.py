"""Card swipe generator — normal POS transactions."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


class CardSwipeGenerator(BaseGenerator):
    """Generates normal card-present transactions at POS terminals.

    Amounts vary realistically based on merchant category — grocery stores
    have smaller average amounts than electronics stores.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        amount = self._pick_amount(merchant.avg_amount_min, merchant.avg_amount_max)
        lat, lon = self._jitter_location(merchant.lat, merchant.lon, km_radius=0.5)

        auth = random.choice([AuthMethod.CHIP, AuthMethod.CONTACTLESS, AuthMethod.SWIPE])
        device = random.choice(customer.devices) if customer.devices else self._make_device_fingerprint()
        ip = random.choice(customer.usual_ips) if customer.usual_ips else self._random_ip()

        return Transaction(
            customer_id=customer.customer_id,
            merchant_id=merchant.merchant_id,
            amount=amount,
            currency="USD",
            transaction_type=TransactionType.CARD_SWIPE,
            timestamp=timestamp,
            merchant_category=merchant.category,
            merchant_name=merchant.name,
            merchant_country=merchant.country,
            merchant_city=merchant.city,
            customer_lat=lat,
            customer_lon=lon,
            device_id=device,
            device_fingerprint=device,
            ip_address=ip,
            channel=Channel.POS,
            is_international=merchant.country != customer.home_country,
            card_present=True,
            authentication_method=auth,
            risk_indicators={},
            metadata={"generator": "card_swipe", "merchant_category_name": merchant.category_name},
            is_fraud=False,
            fraud_type=None,
        )
