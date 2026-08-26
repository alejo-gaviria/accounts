"""SQL implementation of the UnitOfWork port.

Owns the session/transaction boundary only (see the updated
application/gateways/unit_of_work.py port docstring for why it no
longer aggregates `.accounts`/`.ledgers`). Publishes its session as the
"current" one via session_context for the duration of `async with
uow:`, so the singleton SqlAccountRepository/SqlLedgerRepository can
find and use it.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.account_balance.adapters.outbound.repositories.sql.session_context import (
    reset_current_session,
    set_current_session,
)


class SqlUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._session_token = None

    async def __aenter__(self) -> "SqlUnitOfWork":
        self._session = self._session_factory()
        self._session_token = set_current_session(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        assert self._session is not None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            reset_current_session(self._session_token)
            await self._session.close()
            self._session = None
            self._session_token = None
        return False  # never suppress exceptions

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
