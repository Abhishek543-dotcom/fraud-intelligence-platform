"""Burst fraud (card testing attack) generator."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


class BurstFraudGenerator(BaseGenerator):
    """Generates card testing attack transactions.

    Simulates rapid small-value transactions (<$5) across different
    merchants in quick succession — a pattern used by fraudsters to
    verify that stolen card numbers are valid before making large
    purchases.
    """

    # Small amounts used to test if card works
    TEST_AMOUNTS = [0.50, 0.99, 1.00, 1.50, 1.99, 2.00, 2.50, 3.00, 3.49, 4.00, 4.99]

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        amount = Decimal(str(random.choice(self.TEST_AMOUNTS)))
        new_device = self._make_device_fingerprint()
        new_ip = self._random_ip()

        return Transaction(
            customer_id=customer.customer_id,
            merchant_id=merchant.merchant_id,
            amount=amount,
            currency="USD",
            transaction_type=TransactionType.ONLINE_PURCHASE,
            timestamp=timestamp,
            merchant_category=merchant.category,
            merchant_name=merchant.name,
            merchant_country=merchant.country,
            merchant_city=merchant.city,
            customer_lat=merchant.lat + random.gauss(0, 0.1),
            customer_lon=merchant.lon + random.gauss(0, 0.1),
            device_id=new_device,
            device_fingerprint=new_device,
            ip_address=new_ip,
            channel=Channel.WEB,
            is_international=random.random() > 0.5,
            card_present=False,
            authentication_method=AuthMethod.NONE,
            risk_indicators={
                "card_testing": True,
                "low_amount": True,
                "rapid_succession": True,
            },
            metadata={"generator": "burst_fraud"},
            is_fraud=True,
            fraud_type="card_testing",
        )
