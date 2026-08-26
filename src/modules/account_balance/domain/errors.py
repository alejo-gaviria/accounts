from decimal import Decimal
from uuid import UUID


class DomainError(Exception):
    """Base class for all account_balance domain errors."""


class InvalidAmount(DomainError):
    def __init__(self, amount: Decimal) -> None:
        self.amount = amount
        super().__init__(f"Amount must be > 0, got {amount!r}")


class InsufficientFunds(DomainError):
    def __init__(self, account_id: UUID, balance: Decimal, amount: Decimal) -> None:
        self.account_id = account_id
        self.balance = balance
        self.amount = amount
        super().__init__(
            f"Account {account_id} has insufficient funds: "
            f"balance={balance}, requested={amount}"
        )


class UnknownAccount(DomainError):
    def __init__(self, account_id: UUID) -> None:
        self.account_id = account_id
        super().__init__(f"Unknown account: {account_id}")


class UnsupportedCurrency(DomainError):
    def __init__(self, currency: str) -> None:
        self.currency = currency
        super().__init__(f"Unsupported currency: {currency}")
