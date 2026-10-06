"""Delivery provider abstraction.

The MVP ships one simulated provider. A real courier integration implements the same
protocol (quote + create_shipment) and is registered in PROVIDERS; nothing else changes.
"""

import secrets
import string
from dataclasses import dataclass
from typing import Literal, Protocol

District = Literal[
    "COLOMBO", "GAMPAHA", "KALUTARA", "KANDY", "MATALE", "NUWARA_ELIYA", "GALLE", "MATARA",
    "HAMBANTOTA", "JAFFNA", "KILINOCHCHI", "MANNAR", "VAVUNIYA", "MULLAITIVU", "BATTICALOA",
    "AMPARA", "TRINCOMALEE", "KURUNEGALA", "PUTTALAM", "ANURADHAPURA", "POLONNARUWA", "BADULLA",
    "MONERAGALA", "RATNAPURA", "KEGALLE",
]  # fmt: skip


@dataclass(frozen=True)
class DeliveryQuote:
    provider_code: str
    fee_lkr: int
    eta_days: int


class DeliveryProvider(Protocol):
    code: str

    def quote(self, district: District) -> DeliveryQuote: ...

    def create_shipment(self, order_number: str) -> str:
        """Books the shipment and returns the provider's tracking reference."""
        ...


class SimulatedProvider:
    """Flat fees by zone; no external calls. Status updates are entered by the SME."""

    code = "SIMULATED"
    _ZONES: dict[str, tuple[int, int]] = {  # district -> (fee LKR, ETA days)
        "COLOMBO": (350, 2),
        "GAMPAHA": (400, 2),
        "KALUTARA": (400, 2),
        **{
            d: (600, 4)
            for d in (
                "JAFFNA",
                "KILINOCHCHI",
                "MANNAR",
                "VAVUNIYA",
                "MULLAITIVU",
                "BATTICALOA",
                "AMPARA",
                "TRINCOMALEE",
            )
        },  # fmt: skip
    }
    _DEFAULT = (500, 3)

    def quote(self, district: District) -> DeliveryQuote:
        fee, eta = self._ZONES.get(district, self._DEFAULT)
        return DeliveryQuote(provider_code=self.code, fee_lkr=fee, eta_days=eta)

    def create_shipment(self, order_number: str) -> str:
        suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        return f"SIM-{suffix}"


PROVIDERS: dict[str, DeliveryProvider] = {SimulatedProvider.code: SimulatedProvider()}
DEFAULT_PROVIDER = SimulatedProvider.code


def get_provider(code: str = DEFAULT_PROVIDER) -> DeliveryProvider:
    return PROVIDERS[code]
