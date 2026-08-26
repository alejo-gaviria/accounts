"""Credit use case.

Amount/currency are converted to MXN once, before the unit of work
even opens, so an unsupported currency never takes a DB lock.
Everything after that point operates purely in MXN; the original
request values are threaded through only for the ledger's audit
columns. A normal return commits (via the UoW's exception-driven
__aexit__); a propagating domain error rolls back.
"""

from decimal import Decimal
from uuid import UUID

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


class CreditAccountUseCase:
    def __init__(self, uow: UnitOfWork, exchange_rates: StaticExchangeRates) -> None:
        self._uow = uow
        self._exchange_rates = exchange_rates

    async def execute(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> LedgerEntry:
        # Raises UnsupportedCurrency before any DB work at all.
        converted_amount, rate_used = self._exchange_rates.to_mxn(amount, currency)
        money = Money(converted_amount, "MXN")  # raises InvalidAmount if amount <= 0

        async with self._uow as uow:
            account = await uow.accounts.get_for_update(account_id)

            # The row lock above serializes concurrent requests for this
            # account, so checking for an existing entry before mutating
            # the aggregate is race-safe and avoids mutating `account`
            # for a request that turns out to be a pure replay.
            existing = await uow.ledger.find_by_idempotency_key(
                account_id, idempotency_key
            )
            if existing is not None:
                return existing

            entry = account.apply_credit(
                money,
                idempotency_key,
                original_amount=amount,
                original_currency=currency.upper(),
                fx_rate=rate_used,
            )

            result, is_replay = await append_with_replay(uow.ledger, entry)
            if is_replay:
                # Defense in depth: a concurrent request won the race
                # between our check above and this insert. Should not
                # happen given the row lock, but the unique constraint
                # is the ultimate arbiter either way.
                return result

            await uow.accounts.save(account)
            return result
