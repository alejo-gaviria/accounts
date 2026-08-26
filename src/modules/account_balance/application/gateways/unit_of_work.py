"""Port: UnitOfWork — one DB transaction boundary.

Under the dependency-injector refactor, UnitOfWork ONLY owns the
transaction boundary; it no longer aggregates `.accounts`/`.ledgers`
attributes. Use cases receive the repositories as their own separate
constructor-injected dependencies (AccountBalanceContainer wires
account_repository_provider / ledger_repository_provider directly into
each use-case provider, alongside unit_of_work_provider) and call
`uow.commit()`/`uow.rollback()` for the transaction boundary while
calling repository methods directly.

Repositories still operate on the SAME underlying DB session as the
currently-open UnitOfWork — see
adapters/outbound/repositories/sql/session_context.py for how the SQL
adapter makes that true despite the repos being process-lifetime
singletons.

Contract:
- `async with uow:` opens the transaction.
- Use cases MUST call `await uow.commit()` explicitly on the success
  path. If the `with` block exits (normally or via exception) without
  a prior `commit()`, the adapter rolls back — "safe by default".
- Locking two accounts (transfer) happens by calling
  `account_repository.get_for_update()` twice, in ascending account-id
  order, within the same `async with uow:` block.
"""

from typing import Protocol


class UnitOfWork(Protocol):
    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(self, exc_type, exc, tb) -> bool | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
