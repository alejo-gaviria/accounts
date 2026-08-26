"""Port: UnitOfWork — one DB transaction, owning its own repositories.

Everything is injected, nothing ambient: the container gives
SqlUnitOfWork a `session_factory` and a `logger`; `__aenter__` creates
the session AND constructs SqlAccountRepository/SqlLedgerRepository
right there, passing them the session + logger. Repos are plain
classes built fresh per transaction — never container-level
singletons, never resolved from a contextvar or any other ambient
state. Classic Unit-of-Work-owns-Repositories.

Transaction outcome is exception-driven: exiting `async with uow:`
normally commits; exiting via an exception rolls back. There is no
separate `commit()`/`rollback()` method on this port — use cases don't
call either explicitly, they just return normally or let a domain
error propagate.
"""

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

    async def __aexit__(self, exc_type, exc, tb) -> bool | None: ...
