from decimal import Decimal
from logging import Logger
from uuid import UUID

from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.ledger_repo import (
    SqlLedgerRepository,
)
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money
from src.modules.shared.application.ports.unit_of_work import UnitOfWork


class DebitAccountUseCase:
    def __init__(
        self, uow: UnitOfWork, logger: Logger, exchange_rates: StaticExchangeRates
    ) -> None:
        self._uow = uow
        self._logger = logger
        self._exchange_rates = exchange_rates

    async def execute(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> LedgerEntry:
        converted_amount, rate_used = self._exchange_rates.to_mxn(amount, currency)
        money = Money(converted_amount, "MXN")

        async with self._uow as uow:
            accounts = SqlAccountRepository(session=uow.session, logger=self._logger)
            ledger = SqlLedgerRepository(session=uow.session, logger=self._logger)

            account = await accounts.get_for_update(account_id)

            existing = await ledger.find_by_idempotency_key(account_id, idempotency_key)
            if existing is not None:
                return existing

            entry = account.apply_debit(
                money,
                idempotency_key,
                original_amount=amount,
                original_currency=currency.upper(),
                fx_rate=rate_used,
            )

            result, is_replay = await append_with_replay(ledger, entry)
            if is_replay:
                return result

            await accounts.save(account)
            return result
