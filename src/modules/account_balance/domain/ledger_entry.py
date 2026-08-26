"""Immutable LedgerEntry — the in-process mirror of an append-only
`ledger_entries` row.

Frozen by construction: once created it cannot be mutated, matching the
requirement that ledger rows are never updated or deleted.

original_amount/original_currency/fx_rate are audit-only columns:
`amount` is always MXN post-conversion, but reconstructing what the
caller actually sent from an MXN-only amount would otherwise be
impossible for an immutable financial ledger. original_currency/fx_rate
default to the "no conversion happened" case (MXN, rate 1);
original_amount has no such default since it varies per call.
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
