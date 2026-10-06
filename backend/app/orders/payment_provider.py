"""Sandbox payments. No real money moves and no card data is collected or stored.

* COD       — payment is PENDING until the order is delivered, then marked PAID (collected).
* MOCK_CARD — simulated instant success at checkout (PAID); refunds are simulated on cancel.

A real gateway would replace `authorize`/`refund` behind the same interface.
"""

import secrets
import string
from dataclasses import dataclass
from typing import Literal

PaymentMethod = Literal["COD", "MOCK_CARD"]


@dataclass(frozen=True)
class PaymentResult:
    status: Literal["PENDING", "PAID"]
    mock_reference: str | None


def _reference() -> str:
    return "MOCK-" + "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10)
    )


def authorize(method: PaymentMethod) -> PaymentResult:
    if method == "MOCK_CARD":
        return PaymentResult(status="PAID", mock_reference=_reference())
    return PaymentResult(status="PENDING", mock_reference=None)
