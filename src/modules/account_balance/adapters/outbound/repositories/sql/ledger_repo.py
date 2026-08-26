"""SQL implementation of the LedgerRepository port.

Insert/select only — deliberately no update/delete methods exist on
this class at all, mirroring the DB-level append-only grant (the
accounts_app role has no UPDATE/DELETE on ledger_entries; see the
initial migration). Plain class taking session and logger via
constructor injection; built fresh by SqlUnitOfWork.__aenter__ for
every transaction, never a container-level singleton.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.account_balance.adapters.outbound.repositories.sql.dbos.ledger_entry import (
    LedgerEntryRow,
)
from src.modules.account_balance.application.gateways.ledger_repository import (
    DuplicateIdempotencyKey,
    LedgerRepository,
)
from src.modules.account_balance.domain.ledger_entry import EntryType, LedgerEntry
from src.modules.account_balance.domain.money import Money

_UNIQUE_IDEMPOTENCY_CONSTRAINT = "uq_ledger_acct_idem"


class SqlLedgerRepository(LedgerRepository):
    def __init__(self, session: AsyncSession, logger: logging.Logger) -> None:
        self._session = session
        self._logger = logger

    async def append(self, entry: LedgerEntry) -> None:
        row = LedgerEntryRow.from_domain(entry)
        self._session.add(row)
        try:
            # flush (not commit) - stays inside the caller's transaction;
            # this only needs to prove the unique constraint, not end
            # the unit of work.
            await self._session.flush()
        except IntegrityError as exc:
            # A failed flush leaves the session unusable until rolled
            # back (SQLAlchemy requirement) - roll back just far enough
            # to let the caller run find_by_idempotency_key() next in
            # the same unit-of-work block. SqlUnitOfWork.__aexit__ still
            # governs the whole transaction/session lifetime.
            await self._session.rollback()

            constraint_name = getattr(
                getattr(exc, "orig", None), "constraint_name", None
            )
            if constraint_name == _UNIQUE_IDEMPOTENCY_CONSTRAINT:
                self._logger.info(
                    "duplicate idempotency key account_id=%s key=%s",
                    entry.account_id,
                    entry.idempotency_key,
                )
                raise DuplicateIdempotencyKey(
                    entry.account_id, entry.idempotency_key
                ) from exc
            raise

    async def find_by_idempotency_key(
            self, account_id: UUID, idempotency_key: str
    ) -> LedgerEntry | None:
        stmt = select(LedgerEntryRow).where(
            LedgerEntryRow.account_id == account_id,
            LedgerEntryRow.idempotency_key == idempotency_key,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        return LedgerEntry(
            id=row.id,
            account_id=row.account_id,
            entry_type=EntryType(row.entry_type),
            amount=Money(row.amount, row.currency),
            balance_after=row.balance_after,
            idempotency_key=row.idempotency_key,
            transfer_id=row.transfer_id,
            created_at=row.created_at,
            original_amount=row.original_amount,
            original_currency=row.original_currency,
            fx_rate=row.fx_rate,
        )
