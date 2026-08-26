"""SQL implementation of the AccountRepository port.

Plain class taking its session and logger via constructor injection.
Built fresh by SqlUnitOfWork.__aenter__ for every transaction — never a
container-level singleton, never resolved from ambient/global state.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.modules.account_balance.adapters.outbound.repositories.sql.dbos.account import (
    AccountRow,
)
from src.modules.account_balance.application.gateways.account_repository import AccountRepository
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import UnknownAccount


class SqlAccountRepository(AccountRepository):
    def __init__(self, session: AsyncSession, logger: logging.Logger) -> None:
        self._session = session
        self._logger = logger
        self._locked_rows: dict[UUID, AccountRow] = {}

    async def get_for_update(self, account_id: UUID) -> Account:
        stmt = select(AccountRow).where(AccountRow.id == account_id).with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            self._logger.info("account not found id=%s", account_id)
            raise UnknownAccount(account_id)

        self._locked_rows[account_id] = row
        self._logger.debug(
            "locked account id=%s balance=%s", account_id, row.balance
        )
        return Account(
            id=row.id,
            currency=row.currency,
            balance=row.balance,
            version=row.version,
        )

    async def save(self, account: Account) -> None:
        row = self._locked_rows.get(account.id)
        if row is None:
            # Defensive: save() called for an account never locked via
            # get_for_update() on this transaction - not a valid call
            # sequence for any use case in this module.
            raise UnknownAccount(account.id)

        row.balance = account.balance
        row.version = account.version
        row.updated_at = func.now()
        self._logger.debug(
            "saved account id=%s new_balance=%s", account.id, account.balance
        )

    async def create(self, account: Account) -> None:
        data = AccountRow.from_domain(account)
        self._session.add(data)
        await self._session.flush()
        self._logger.info(
            "created dummy account id=%s balance=%s currency=%s",
            account.id,
            account.balance,
            account.currency,
        )
