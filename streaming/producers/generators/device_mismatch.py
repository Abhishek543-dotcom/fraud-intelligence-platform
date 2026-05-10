"""Device mismatch fraud generator."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


class DeviceMismatchGenerator(BaseGenerator):
    """Generates device mismatch fraud transactions.

    Simulates a transaction from the customer's account but using
    a completely unknown device fingerprint and a new IP address
    range — indicating potential account takeover.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        amount = self._pick_amount(100.0, 3000.0)

        # Use a brand-new device and IP that the customer has never used
        new_device = self._make_device_fingerprint()
        new_ip = self._random_ip()

        # Ensure the new device is NOT in the customer's known devices
        while new_device in customer.devices:
            new_device = self._make_device_fingerprint()

        channel = random.choice([Channel.WEB, Channel.MOBILE])
        auth = random.choice([AuthMethod.PASSWORD, AuthMethod.NONE])

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
            customer_lat=customer.home_lat + random.gauss(0, 0.5),
            customer_lon=customer.home_lon + random.gauss(0, 0.5),
            device_id=new_device,
            device_fingerprint=new_device,
            ip_address=new_ip,
            channel=channel,
            is_international=merchant.country != customer.home_country,
            card_present=False,
            authentication_method=auth,
            risk_indicators={
                "new_device": True,
                "new_ip": True,
                "known_devices": len(customer.devices),
            },
            metadata={"generator": "device_mismatch"},
            is_fraud=True,
            fraud_type="device_fraud",
        )
