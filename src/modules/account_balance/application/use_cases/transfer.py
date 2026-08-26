"""Transfer use case.

Both account locks are acquired in ascending-id order to avoid
deadlocking against a concurrent transfer running in the opposite
direction between the same two accounts. Both legs share one
transfer_id; per-leg idempotency keys are derived from the single
request Idempotency-Key. Amount/currency are converted to MXN once,
before either leg is applied, since every account is MXN-denominated.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.services.idempotency import (
    append_with_replay,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry
from src.modules.account_balance.domain.money import Money


@dataclass(frozen=True)
class TransferResult:
    transfer_id: UUID
    debit_entry: LedgerEntry
    credit_entry: LedgerEntry | None


class TransferUseCase:
    def __init__(self, uow: UnitOfWork, exchange_rates: StaticExchangeRates) -> None:
        self._uow = uow
        self._exchange_rates = exchange_rates

    async def execute(
        self,
        from_account_id: UUID,
        to_account_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> TransferResult:
        converted_amount, rate_used = self._exchange_rates.to_mxn(amount, currency)
        money = Money(converted_amount, "MXN")
        original_currency = currency.upper()

        debit_key = f"{idempotency_key}#debit"
        credit_key = f"{idempotency_key}#credit"

        first_id, second_id = sorted((from_account_id, to_account_id))

        async with self._uow as uow:
            locked = {
                first_id: await uow.accounts.get_for_update(first_id),
                second_id: await uow.accounts.get_for_update(second_id),
            }
            from_account = locked[from_account_id]
            to_account = locked[to_account_id]

            existing_debit = await uow.ledger.find_by_idempotency_key(
                from_account_id, debit_key
            )
            if existing_debit is not None:
                existing_credit = await uow.ledger.find_by_idempotency_key(
                    to_account_id, credit_key
                )
                return TransferResult(
                    existing_debit.transfer_id, existing_debit, existing_credit
                )

            transfer_id = uuid4()

            # May raise InsufficientFunds — propagates, no rows written.
            debit_entry = from_account.apply_debit(
                money,
                debit_key,
                transfer_id=transfer_id,
                original_amount=amount,
                original_currency=original_currency,
                fx_rate=rate_used,
            )
            debit_result, debit_replay = await append_with_replay(
                uow.ledger, debit_entry
            )
            if debit_replay:
                existing_credit = await uow.ledger.find_by_idempotency_key(
                    to_account_id, credit_key
                )
                return TransferResult(
                    debit_result.transfer_id, debit_result, existing_credit
                )

            credit_entry = to_account.apply_credit(
                money,
                credit_key,
                transfer_id=transfer_id,
                original_amount=amount,
                original_currency=original_currency,
                fx_rate=rate_used,
            )
            credit_result, credit_replay = await append_with_replay(
                uow.ledger, credit_entry
            )
            if credit_replay:
                # Defensive only: the debit leg above already proved
                # this is a new key pair, so this should not occur in
                # practice.
                return TransferResult(transfer_id, debit_result, credit_result)

            await uow.accounts.save(from_account)
            await uow.accounts.save(to_account)
            return TransferResult(transfer_id, debit_result, credit_result)
