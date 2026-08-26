"""Debit use case.

Spec: balance-mutation-api / Insufficient funds on debit/transfer -
rejected with no state change; balance-mutation-api / Successful
credit's debit counterpart otherwise.
"""

from uuid import UUID

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


async def debit(
    uow: UnitOfWork,
    account_id: UUID,
    money: Money,
    idempotency_key: str,
) -> LedgerEntry:
    async with uow:
        account = await uow.accounts.get_for_update(account_id)

        existing = await uow.ledgers.find_by_idempotency_key(
            account_id, idempotency_key
        )
        if existing is not None:
            await uow.rollback()
            return existing

        # May raise InsufficientFunds — propagates out of this `async
        # with` block, triggering the UoW's default rollback-on-exit,
        # with no ledger row ever constructed or appended (spec: "no
        # state change").
        entry = account.apply_debit(money, idempotency_key)

        result, is_replay = await append_with_replay(uow.ledgers, entry)
        if is_replay:
            await uow.rollback()
            return result

        await uow.accounts.save(account)
        await uow.commit()
        return result
