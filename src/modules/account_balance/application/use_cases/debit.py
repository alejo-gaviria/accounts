"""Debit use case.

Spec: balance-mutation-api / Insufficient funds on debit/transfer -
rejected with no state change; balance-mutation-api / Successful
credit's debit counterpart otherwise.

House convention (design.md "Dependency Injection"): class with its
UnitOfWork injected via constructor, wired via AccountBalanceContainer
as a `providers.Factory`.
"""

from uuid import UUID

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


class DebitAccountUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, account_id: UUID, money: Money, idempotency_key: str
    ) -> LedgerEntry:
        async with self._uow as uow:
            account = await uow.accounts.get_for_update(account_id)

            existing = await uow.ledger.find_by_idempotency_key(
                account_id, idempotency_key
            )
            if existing is not None:
                return existing

            # May raise InsufficientFunds — propagates out of this
            # `async with` block, so the UoW's __aexit__ rolls back
            # (exception present), with no ledger row ever constructed
            # or appended (spec: "no state change").
            entry = account.apply_debit(money, idempotency_key)

            result, is_replay = await append_with_replay(uow.ledger, entry)
            if is_replay:
                return result

            await uow.accounts.save(account)
            return result
