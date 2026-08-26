import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.ledger_repo import (
    SqlLedgerRepository,
)
from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork


class SqlUnitOfWork(UnitOfWork):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: logging.Logger,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger
        self.session: AsyncSession | None = None  #type: ignore[assignment]
        self.accounts: SqlAccountRepository | None = None
        self.ledger: SqlLedgerRepository | None = None

    async def __aenter__(self) -> "SqlUnitOfWork":
        self.session = self._session_factory()
        await self.session.begin()
        self.accounts = SqlAccountRepository(session=self.session, logger=self._logger)
        self.ledger = SqlLedgerRepository(session=self.session, logger=self._logger)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
