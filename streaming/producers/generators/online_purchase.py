"""Online purchase generator."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


class OnlinePurchaseGenerator(BaseGenerator):
    """Generates legitimate online/e-commerce transactions.

    Transaction amounts vary by time of day — higher during evening hours
    when customers are more likely to make deliberate purchases.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        # Evening purchases tend to be higher value
        hour = timestamp.hour
        if 18 <= hour <= 23:
            multiplier = random.uniform(1.0, 1.5)
        elif 0 <= hour <= 6:
            multiplier = random.uniform(0.3, 0.7)
        else:
            multiplier = random.uniform(0.6, 1.2)

        base = random.uniform(merchant.avg_amount_min, merchant.avg_amount_max)
        amount = Decimal(str(round(base * multiplier, 2)))

        device = random.choice(customer.devices) if customer.devices else self._make_device_fingerprint()
        ip = random.choice(customer.usual_ips) if customer.usual_ips else self._random_ip()
        channel = random.choice([Channel.WEB, Channel.MOBILE])
        auth = random.choice([AuthMethod.PASSWORD, AuthMethod.TWO_FACTOR, AuthMethod.BIOMETRIC])

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
            customer_lat=customer.home_lat,
            customer_lon=customer.home_lon,
            device_id=device,
            device_fingerprint=device,
            ip_address=ip,
            channel=channel,
            is_international=merchant.country != customer.home_country,
            card_present=False,
            authentication_method=auth,
            risk_indicators={},
            metadata={"generator": "online_purchase", "session_hour": hour},
            is_fraud=False,
            fraud_type=None,
        )
