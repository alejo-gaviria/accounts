"""Money value object: a positive amount with a currency code.

Mirrors the DB-level `amount NUMERIC(20,4) CHECK (amount > 0)` constraint
on `ledger_entries` (design.md) — Money always represents a positive
mutation magnitude; direction (credit/debit) is carried separately by
`EntryType` on `LedgerEntry`.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.modules.account_balance.domain.errors import InvalidAmount


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise InvalidAmount(self.amount)
        if len(self.currency) != 3:
            raise ValueError(
                f"currency must be a 3-letter code, got {self.currency!r}"
            )
