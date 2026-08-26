"""Immutable LedgerEntry — the in-process mirror of an append-only
`ledger_entries` row (design.md schema).

Frozen by construction: once created it cannot be mutated, matching the
spec requirement that ledger rows are never UPDATEd/DELETEd.

original_amount/original_currency/fx_rate (design.md "Currency
Conversion") are audit-only columns: `amount` is always MXN
post-conversion, but reconstructing "what did the caller actually
send" from an MXN-only amount would otherwise be impossible - which
matters for an immutable financial ledger. original_currency/fx_rate
default to the "no conversion happened" case (MXN, rate 1);
original_amount has no such default - callers must state it explicitly
(see domain/account.py's apply_credit/apply_debit, which default it to
`money.amount` when not given).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from src.modules.account_balance.domain.money import Money


class EntryType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


@dataclass(frozen=True)
class LedgerEntry:
    account_id: UUID
    entry_type: EntryType
    amount: Money
    balance_after: Decimal
    idempotency_key: str
    original_amount: Decimal
    original_currency: str = "MXN"
    fx_rate: Decimal = Decimal("1")
    id: UUID = field(default_factory=uuid4)
    transfer_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
