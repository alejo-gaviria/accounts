"""SQL implementation of the UnitOfWork port.

Owns the transaction boundary (one AsyncSession per `async with`
block). The ascending-account-id lock ordering for transfers is
enforced by the caller (application/use_cases/transfer.py calling
`accounts.get_for_update()` twice, lowest id first) — this class only
needs to make sure both calls share the same session/transaction, which
it does simply by handing out one `SqlAccountRepository` bound to this
unit of work's session.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.ledger_repo import (
    SqlLedgerRepository,
)


class SqlUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.accounts: SqlAccountRepository
        self.ledgers: SqlLedgerRepository

    async def __aenter__(self) -> "SqlUnitOfWork":
        self._session = self._session_factory()
        self.accounts = SqlAccountRepository(self._session)
        self.ledgers = SqlLedgerRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        assert self._session is not None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
        return False  # never suppress exceptions

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
