"""Debit use case.

Spec: balance-mutation-api / Insufficient funds on debit/transfer -
rejected with no state change; balance-mutation-api / Successful
credit's debit counterpart otherwise.

House convention (design.md "Dependency Injection"): class with
constructor-injected dependencies, wired via AccountBalanceContainer as
a `providers.Factory`.
"""

from uuid import UUID

from src.modules.account_balance.application.gateways.account_repository import (
    AccountRepository,
)
from src.modules.account_balance.application.gateways.ledger_repository import (
    LedgerRepository,
)
from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


class DebitAccountUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        account_repository: AccountRepository,
        ledger_repository: LedgerRepository,
    ) -> None:
        self._uow = uow
        self._accounts = account_repository
        self._ledgers = ledger_repository

    async def execute(
        self, account_id: UUID, money: Money, idempotency_key: str
    ) -> LedgerEntry:
        async with self._uow:
            account = await self._accounts.get_for_update(account_id)

            existing = await self._ledgers.find_by_idempotency_key(
                account_id, idempotency_key
            )
            if existing is not None:
                await self._uow.rollback()
                return existing

            # May raise InsufficientFunds — propagates out of this
            # `async with` block, triggering the UoW's default
            # rollback-on-exit, with no ledger row ever constructed or
            # appended (spec: "no state change").
            entry = account.apply_debit(money, idempotency_key)

            result, is_replay = await append_with_replay(self._ledgers, entry)
            if is_replay:
                await self._uow.rollback()
                return result

            await self._accounts.save(account)
            await self._uow.commit()
            return result
