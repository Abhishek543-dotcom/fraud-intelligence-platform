"""Mule account fraud generator."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator


class MuleAccountGenerator(BaseGenerator):
    """Generates mule account fraud transactions.

    Simulates the withdrawal phase of a money mule pattern:
    a large outbound transfer after receiving many small deposits
    from multiple senders. The mule withdraws or transfers the
    aggregated funds quickly.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        # Mule withdrawals tend to be large, rounded amounts
        amount_choices = [500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
        amount = Decimal(str(random.choice(amount_choices)))

        device = random.choice(customer.devices) if customer.devices else self._make_device_fingerprint()
        ip = random.choice(customer.usual_ips) if customer.usual_ips else self._random_ip()

        # Mule accounts often use wire transfers or P2P
        tx_type = random.choice([TransactionType.WIRE_TRANSFER, TransactionType.P2P])
        channel = random.choice([Channel.WEB, Channel.MOBILE, Channel.BRANCH])

        num_recent_deposits = random.randint(5, 20)

        return Transaction(
            customer_id=customer.customer_id,
            merchant_id=merchant.merchant_id,
            amount=amount,
            currency="USD",
            transaction_type=tx_type,
            timestamp=timestamp,
            merchant_category="6012",  # Financial institution MCC
            merchant_name="Wire Transfer Service",
            merchant_country=customer.home_country,
            merchant_city=customer.home_city,
            customer_lat=customer.home_lat,
            customer_lon=customer.home_lon,
            device_id=device,
            device_fingerprint=device,
            ip_address=ip,
            channel=channel,
            is_international=False,
            card_present=channel == Channel.BRANCH,
            authentication_method=AuthMethod.TWO_FACTOR,
            risk_indicators={
                "mule_pattern": True,
                "recent_inbound_deposits": num_recent_deposits,
                "withdrawal_to_deposit_ratio": round(float(amount) / max(1, num_recent_deposits * 50), 2),
            },
            metadata={"generator": "mule_account", "recent_deposits": num_recent_deposits},
            is_fraud=True,
            fraud_type="mule_account",
        )
