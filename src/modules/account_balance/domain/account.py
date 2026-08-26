"""Account aggregate: owns the balance invariant (balance >= 0) and
produces LedgerEntry rows for its own mutations.

This is a pure in-memory aggregate — persistence (the SELECT ... FOR
UPDATE lock, the INSERT/UPDATE pair, the transaction boundary) is owned
by the application layer's use cases and the SQL unit of work
(design.md "Concurrency + Idempotency Protocol"), not by this class.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from src.modules.account_balance.domain.errors import InsufficientFunds
from src.modules.account_balance.domain.ledger_entry import EntryType, LedgerEntry
from src.modules.account_balance.domain.money import Money


@dataclass
class Account:
    id: UUID = field(default_factory=uuid4)
    currency: str = "USD"
    balance: Decimal = Decimal("0")
    version: int = 0

    def apply_credit(
        self,
        money: Money,
        idempotency_key: str,
        transfer_id: UUID | None = None,
    ) -> LedgerEntry:
        new_balance = self.balance + money.amount
        entry = LedgerEntry(
            account_id=self.id,
            entry_type=EntryType.CREDIT,
            amount=money,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            transfer_id=transfer_id,
        )
        self.balance = new_balance
        self.version += 1
        return entry

    def apply_debit(
        self,
        money: Money,
        idempotency_key: str,
        transfer_id: UUID | None = None,
    ) -> LedgerEntry:
        new_balance = self.balance - money.amount
        if new_balance < 0:
            raise InsufficientFunds(self.id, self.balance, money.amount)

        entry = LedgerEntry(
            account_id=self.id,
            entry_type=EntryType.DEBIT,
            amount=money,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            transfer_id=transfer_id,
        )
        self.balance = new_balance
        self.version += 1
        return entry
