"""In-memory test doubles for the application-layer ports.

Phase 4's focused test command is `pytest tests/domain tests/application`
with no live infra ("N/A — pure logic, no live infra needed" per the
tasks.md Suggested Work Units table) — these fakes are what make that
possible. The real Postgres-backed adapters are Phase 5.
"""

from uuid import UUID

from src.modules.account_balance.application.gateways.ledger_repository import (
    DuplicateIdempotencyKey,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import UnknownAccount
from src.modules.account_balance.domain.ledger_entry import LedgerEntry


class FakeAccountRepository:
    def __init__(self, accounts: dict[UUID, Account]) -> None:
        self._accounts = accounts
        self.lock_order: list[UUID] = []
        self.saved: list[Account] = []

    async def get_for_update(self, account_id: UUID) -> Account:
        self.lock_order.append(account_id)
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    async def save(self, account: Account) -> None:
        self.saved.append(account)
        self._accounts[account.id] = account


class FakeLedgerRepository:
    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    async def append(self, entry: LedgerEntry) -> None:
        for existing in self.entries:
            if (
                existing.account_id == entry.account_id
                and existing.idempotency_key == entry.idempotency_key
            ):
                raise DuplicateIdempotencyKey(
                    entry.account_id, entry.idempotency_key
                )
        self.entries.append(entry)

    async def find_by_idempotency_key(
        self, account_id: UUID, idempotency_key: str
    ) -> LedgerEntry | None:
        for entry in self.entries:
            if (
                entry.account_id == account_id
                and entry.idempotency_key == idempotency_key
            ):
                return entry
        return None


class FakeUnitOfWork:
    def __init__(
        self, accounts: FakeAccountRepository, ledgers: FakeLedgerRepository
    ) -> None:
        self.accounts = accounts
        self.ledgers = ledgers
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if not self.committed:
            self.rolled_back = True
        return False  # never suppress exceptions

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True
