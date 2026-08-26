"""SQL implementation of the AccountRepository port.

Implements the application/gateways/account_repository.py Protocol.
Wired as a `providers.Singleton` in AccountBalanceContainer — this
class holds no per-request state of its own; it resolves the ambient
session via session_context (set by whichever SqlUnitOfWork is
currently open on this asyncio task) and stashes the ORM rows it locks
on that session's `.info` dict (SQLAlchemy's supported per-session
scratch space), so `save()` can find the same locked row without a
second `SELECT ... FOR UPDATE` round-trip.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func

from src.modules.account_balance.adapters.outbound.repositories.sql.models import (
    AccountRow,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.session_context import (
    get_current_session,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import UnknownAccount

_LOCKED_ROWS_KEY = "account_balance_locked_account_rows"


class SqlAccountRepository:
    async def get_for_update(self, account_id: UUID) -> Account:
        session = get_current_session()
        stmt = select(AccountRow).where(AccountRow.id == account_id).with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise UnknownAccount(account_id)

        session.info.setdefault(_LOCKED_ROWS_KEY, {})[account_id] = row
        return Account(
            id=row.id,
            currency=row.currency,
            balance=row.balance,
            version=row.version,
        )

    async def save(self, account: Account) -> None:
        session = get_current_session()
        locked_rows = session.info.get(_LOCKED_ROWS_KEY, {})
        row = locked_rows.get(account.id)
        if row is None:
            # Defensive: save() called for an account never locked via
            # get_for_update() on this session - not a valid call
            # sequence for any use case in this module.
            raise UnknownAccount(account.id)

        row.balance = account.balance
        row.version = account.version
        row.updated_at = func.now()
