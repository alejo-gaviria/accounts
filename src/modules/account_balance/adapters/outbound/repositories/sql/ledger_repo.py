"""SQL implementation of the LedgerRepository port.

Insert/select only — deliberately no update/delete methods exist on
this class at all, mirroring the DB-level append-only grant (the
accounts_app role has no UPDATE/DELETE on ledger_entries; see the
initial migration).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.account_balance.adapters.outbound.repositories.sql.models import (
    LedgerEntryRow,
)
from src.modules.account_balance.application.gateways.ledger_repository import (
    DuplicateIdempotencyKey,
)
from src.modules.account_balance.domain.ledger_entry import EntryType, LedgerEntry
from src.modules.account_balance.domain.money import Money

_UNIQUE_IDEMPOTENCY_CONSTRAINT = "uq_ledger_acct_idem"


class SqlLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, entry: LedgerEntry) -> None:
        row = LedgerEntryRow(
            id=entry.id,
            account_id=entry.account_id,
            entry_type=entry.entry_type.value,
            amount=entry.amount.amount,
            currency=entry.amount.currency,
            balance_after=entry.balance_after,
            idempotency_key=entry.idempotency_key,
            transfer_id=entry.transfer_id,
        )
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
            # the same unit-of-work block. The outer UnitOfWork's own
            # rollback()/commit() still governs the whole transaction.
            await self._session.rollback()

            constraint_name = getattr(
                getattr(exc, "orig", None), "constraint_name", None
            )
            if constraint_name == _UNIQUE_IDEMPOTENCY_CONSTRAINT:
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
        )
