from typing import Protocol

from src.modules.account_balance.application.gateways.account_repository import (
    AccountRepository,
)
from src.modules.account_balance.application.gateways.ledger_repository import (
    LedgerRepository,
)


class UnitOfWork(Protocol):
    accounts: AccountRepository
    ledger: LedgerRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    # normal exit commits; exception rolls back
    async def __aexit__(self, exc_type, exc, tb) -> bool | None: ...
