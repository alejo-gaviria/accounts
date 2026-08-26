from dataclasses import dataclass
from decimal import Decimal

from src.modules.account_balance.domain.errors import InvalidAmount


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise InvalidAmount(self.amount)
        if len(self.currency) != 3:
            raise ValueError(
                f"currency must be a 3-letter code, got {self.currency!r}"
            )
