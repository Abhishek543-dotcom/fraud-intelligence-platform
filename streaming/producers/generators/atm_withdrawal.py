"""ATM withdrawal generator."""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from ..models.customer import CustomerProfile
from ..models.merchant import MerchantProfile
from ..models.transaction import AuthMethod, Channel, Transaction, TransactionType
from .base import BaseGenerator

# ATM withdrawals are typically in round denominations
ATM_AMOUNTS = [20, 40, 50, 60, 80, 100, 120, 140, 160, 180, 200, 250, 300, 400, 500]


class ATMWithdrawalGenerator(BaseGenerator):
    """Generates legitimate ATM cash withdrawal transactions.

    Amounts are round numbers ($20–$500) reflecting real ATM behavior
    where machines dispense fixed denominations.
    """

    def generate(
        self,
        customer: CustomerProfile,
        merchant: MerchantProfile,
        timestamp: datetime,
    ) -> Transaction:
        amount = Decimal(str(random.choice(ATM_AMOUNTS)))
        lat, lon = self._jitter_location(customer.home_lat, customer.home_lon, km_radius=10.0)
        device = random.choice(customer.devices) if customer.devices else self._make_device_fingerprint()

        return Transaction(
            customer_id=customer.customer_id,
            merchant_id=merchant.merchant_id,
            amount=amount,
            currency="USD",
            transaction_type=TransactionType.ATM_WITHDRAWAL,
            timestamp=timestamp,
            merchant_category="6011",  # ATM MCC
            merchant_name=f"ATM-{merchant.city}",
            merchant_country=merchant.country,
            merchant_city=merchant.city,
            customer_lat=lat,
            customer_lon=lon,
            device_id=device,
            device_fingerprint=device,
            ip_address="0.0.0.0",  # ATMs don't expose customer IP
            channel=Channel.ATM,
            is_international=merchant.country != customer.home_country,
            card_present=True,
            authentication_method=AuthMethod.PIN,
            risk_indicators={},
            metadata={"generator": "atm_withdrawal"},
            is_fraud=False,
            fraud_type=None,
        )
