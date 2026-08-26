"""SQL implementation of the AccountRepository port.

Implements the application/gateways/account_repository.py Protocol.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.modules.account_balance.adapters.outbound.repositories.sql.models import (
    AccountRow,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import UnknownAccount


class SqlAccountRepository:
    """One instance per unit-of-work/session. Caches the ORM row it
    locked via `get_for_update` so `save()` doesn't need a second
    `SELECT ... FOR UPDATE` round-trip against a row this transaction
    already holds the lock on.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._locked_rows: dict[UUID, AccountRow] = {}

    async def get_for_update(self, account_id: UUID) -> Account:
        stmt = select(AccountRow).where(AccountRow.id == account_id).with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise UnknownAccount(account_id)

        self._locked_rows[account_id] = row
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
            # get_for_update() in this transaction — not a valid call
            # sequence for any use case in this module.
            raise UnknownAccount(account.id)

        row.balance = account.balance
        row.version = account.version
        row.updated_at = func.now()
