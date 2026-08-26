from typing import Protocol
from uuid import UUID

from src.modules.account_balance.domain.ledger_entry import LedgerEntry


class DuplicateIdempotencyKey(Exception):
    def __init__(self, account_id: UUID, idempotency_key: str) -> None:
        self.account_id = account_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Duplicate idempotency key {idempotency_key!r} for account {account_id}"
        )


class LedgerRepository(Protocol):
    async def append(self, entry: LedgerEntry) -> None:
        """Insert-only. Raises DuplicateIdempotencyKey on unique violation."""
        ...

    async def find_by_idempotency_key(
        self, account_id: UUID, idempotency_key: str
    ) -> LedgerEntry | None:
        """Used for idempotent replay — returns the original entry, if any."""
        ...
