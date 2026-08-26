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

from src.modules.account_balance.domain.errors import InsufficientFunds, InvalidAmount
from src.modules.account_balance.domain.ledger_entry import EntryType, LedgerEntry
from src.modules.account_balance.domain.money import Money


@dataclass
class Account:
    id: UUID = field(default_factory=uuid4)
    currency: str = "MXN"
    balance: Decimal = Decimal("0")
    version: int = 0

    def __post_init__(self) -> None:
        # Mirrors the DB-level `balance NUMERIC(20,4) CHECK (balance >= 0)`
        # constraint. Unlike Money (used for mutation amounts, which must
        # be strictly > 0), a starting/current balance of exactly 0 is
        # valid — only negative is rejected. This matters now that
        # CreateDummyAccountUseCase constructs a fresh Account with a
        # caller-supplied balance; every other construction path
        # (hydrating from a DB row) already satisfies this trivially.
        if self.balance < 0:
            raise InvalidAmount(self.balance)

    def apply_credit(
        self,
        money: Money,
        idempotency_key: str,
        transfer_id: UUID | None = None,
        original_amount: Decimal | None = None,
        original_currency: str = "MXN",
        fx_rate: Decimal = Decimal("1"),
    ) -> LedgerEntry:
        # original_amount/original_currency/fx_rate are audit-only
        # (design.md "Currency Conversion") - this method doesn't
        # perform or know about any conversion itself, it just threads
        # through whatever the caller already computed (see
        # application/use_cases/credit.py). Left at their defaults,
        # this behaves exactly as before conversion existed: the
        # ledger row simply records that no conversion happened.
        new_balance = self.balance + money.amount
        entry = LedgerEntry(
            account_id=self.id,
            entry_type=EntryType.CREDIT,
            amount=money,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            transfer_id=transfer_id,
            original_amount=original_amount if original_amount is not None else money.amount,
            original_currency=original_currency,
            fx_rate=fx_rate,
        )
        self.balance = new_balance
        self.version += 1
        return entry

    def apply_debit(
        self,
        money: Money,
        idempotency_key: str,
        transfer_id: UUID | None = None,
        original_amount: Decimal | None = None,
        original_currency: str = "MXN",
        fx_rate: Decimal = Decimal("1"),
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
            original_amount=original_amount if original_amount is not None else money.amount,
            original_currency=original_currency,
            fx_rate=fx_rate,
        )
        self.balance = new_balance
        self.version += 1
        return entry
