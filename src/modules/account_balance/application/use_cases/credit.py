"""Credit use case.

Spec: balance-mutation-api / Successful credit.
Protocol (design.md): lock account -> compute+attempt-append ledger
entry (idempotency arbiter) -> on duplicate, rollback+replay; otherwise
save the new balance and commit.
"""

from uuid import UUID

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


async def credit(
    uow: UnitOfWork,
    account_id: UUID,
    money: Money,
    idempotency_key: str,
) -> LedgerEntry:
    async with uow:
        account = await uow.accounts.get_for_update(account_id)

        # Check-then-mutate: the FOR UPDATE lock above already serializes
        # concurrent requests for this account, so checking for an
        # existing entry BEFORE mutating the aggregate is race-safe
        # (design.md ordering note) and avoids mutating `account` for a
        # request that turns out to be a pure replay.
        existing = await uow.ledgers.find_by_idempotency_key(
            account_id, idempotency_key
        )
        if existing is not None:
            await uow.rollback()
            return existing

        entry = account.apply_credit(money, idempotency_key)

        result, is_replay = await append_with_replay(uow.ledgers, entry)
        if is_replay:
            # Defense in depth: a concurrent request won the race between
            # our check above and this insert. Should not happen given
            # the row lock, but the unique constraint is the ultimate
            # arbiter either way.
            await uow.rollback()
            return result

        await uow.accounts.save(account)
        await uow.commit()
        return result
