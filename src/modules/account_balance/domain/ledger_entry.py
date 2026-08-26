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
