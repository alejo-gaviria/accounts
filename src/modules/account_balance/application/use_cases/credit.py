"""Credit use case.

Spec: balance-mutation-api / Successful credit.
Protocol (design.md): lock account -> compute+attempt-append ledger
entry (idempotency arbiter) -> on duplicate, rollback+replay; otherwise
save the new balance and commit.

House convention (design.md "Dependency Injection"): a class with
dependencies injected via constructor, wired through
AccountBalanceContainer as a `providers.Factory` — never a plain
function. The operation itself lives on `.execute(...)`.
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


class CreditAccountUseCase:
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

            # Check-then-mutate: the FOR UPDATE lock above already
            # serializes concurrent requests for this account, so
            # checking for an existing entry BEFORE mutating the
            # aggregate is race-safe (design.md ordering note) and
            # avoids mutating `account` for a request that turns out to
            # be a pure replay.
            existing = await self._ledgers.find_by_idempotency_key(
                account_id, idempotency_key
            )
            if existing is not None:
                await self._uow.rollback()
                return existing

            entry = account.apply_credit(money, idempotency_key)

            result, is_replay = await append_with_replay(self._ledgers, entry)
            if is_replay:
                # Defense in depth: a concurrent request won the race
                # between our check above and this insert. Should not
                # happen given the row lock, but the unique constraint
                # is the ultimate arbiter either way.
                await self._uow.rollback()
                return result

            await self._accounts.save(account)
            await self._uow.commit()
            return result
