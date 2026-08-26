"""Port: UnitOfWork — one DB transaction spanning both repositories.

Contract:
- `async with uow:` opens the transaction (and, in the SQL adapter,
  the `SELECT ... FOR UPDATE` locks happen through `uow.accounts`
  inside this block).
- Use cases MUST call `await uow.commit()` explicitly on the success
  path. If the `with` block exits (normally or via exception) without
  a prior `commit()`, the adapter rolls back — "safe by default".
- Locking two accounts (transfer) happens by calling
  `uow.accounts.get_for_update()` twice, in ascending account-id order,
  within the same `async with uow:` block, so both locks are held by
  the one underlying DB transaction.
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
    ledgers: LedgerRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(self, exc_type, exc, tb) -> bool | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
