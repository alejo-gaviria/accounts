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
        self.created: list[Account] = []

    async def get_for_update(self, account_id: UUID) -> Account:
        self.lock_order.append(account_id)
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    async def save(self, account: Account) -> None:
        self.saved.append(account)
        self._accounts[account.id] = account

    async def create(self, account: Account) -> None:
        self.created.append(account)
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
    def __init__(self) -> None:
        self.session = object()  # opaque placeholder, unused by fakes
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True
        return False


def patch_use_case_repos(monkeypatch, use_case_module, accounts, ledger) -> None:
    # patches module-level names because use cases import repos directly, not via injection
    monkeypatch.setattr(
        use_case_module, "SqlAccountRepository", lambda session, logger: accounts
    )
    monkeypatch.setattr(
        use_case_module, "SqlLedgerRepository", lambda session, logger: ledger
    )
