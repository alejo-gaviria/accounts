"""Credit use case.

Spec: balance-mutation-api / Successful credit.
Protocol (design.md): lock account -> check idempotency -> compute +
append ledger entry -> save balance. Normal return commits (via the
UoW's exception-driven __aexit__); a propagating domain error rolls
back.

House convention (design.md "Dependency Injection"): a class with its
UnitOfWork injected via constructor, wired through
AccountBalanceContainer as a `providers.Factory` — never a plain
function. The operation itself lives on `.execute(...)`.

Currency Conversion (design.md): the caller's requested amount/currency
are converted to MXN via StaticExchangeRates ONCE, at the very start of
execute() — before opening the unit of work at all, so an unsupported
currency never even takes a DB lock. Everything after that point (the
domain, the repositories) operates purely in MXN, unaware conversion
ever happened; the original request values are threaded through only
for the ledger's audit columns.
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

            # Check-then-mutate: the FOR UPDATE lock above already
            # serializes concurrent requests for this account, so
            # checking for an existing entry BEFORE mutating the
            # aggregate is race-safe (design.md ordering note) and
            # avoids mutating `account` for a request that turns out to
            # be a pure replay. Nothing pending -> normal return just
            # commits an empty (no-op) transaction.
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
