"""Transfer use case.

Spec: balance-mutation-api / Successful transfer - source debits and
destination credits atomically with two linked ledger entries.
Design: both account locks acquired in ascending-id order (deadlock
avoidance for concurrent opposite-direction transfers); both legs share
one transfer_id; per-leg idempotency keys are derived from the single
request Idempotency-Key (here: f"{key}#debit" / f"{key}#credit").
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
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


async def transfer(
    uow: UnitOfWork,
    from_account_id: UUID,
    to_account_id: UUID,
    money: Money,
    idempotency_key: str,
) -> TransferResult:
    debit_key = f"{idempotency_key}#debit"
    credit_key = f"{idempotency_key}#credit"

    # Deterministic (ascending id) lock order avoids deadlocking against
    # a concurrent transfer running in the opposite direction between
    # the same two accounts.
    first_id, second_id = sorted((from_account_id, to_account_id))

    async with uow:
        locked = {
            first_id: await uow.accounts.get_for_update(first_id),
            second_id: await uow.accounts.get_for_update(second_id),
        }
        from_account = locked[from_account_id]
        to_account = locked[to_account_id]

        existing_debit = await uow.ledgers.find_by_idempotency_key(
            from_account_id, debit_key
        )
        if existing_debit is not None:
            existing_credit = await uow.ledgers.find_by_idempotency_key(
                to_account_id, credit_key
            )
            await uow.rollback()
            return TransferResult(
                existing_debit.transfer_id, existing_debit, existing_credit
            )

        transfer_id = uuid4()

        # May raise InsufficientFunds — propagates, no rows written.
        debit_entry = from_account.apply_debit(
            money, debit_key, transfer_id=transfer_id
        )
        debit_result, debit_replay = await append_with_replay(
            uow.ledgers, debit_entry
        )
        if debit_replay:
            existing_credit = await uow.ledgers.find_by_idempotency_key(
                to_account_id, credit_key
            )
            await uow.rollback()
            return TransferResult(
                debit_result.transfer_id, debit_result, existing_credit
            )

        credit_entry = to_account.apply_credit(
            money, credit_key, transfer_id=transfer_id
        )
        credit_result, credit_replay = await append_with_replay(
            uow.ledgers, credit_entry
        )
        if credit_replay:
            # Defensive only: the debit leg above already proved this is
            # a new key pair, so this should not occur in practice.
            await uow.rollback()
            return TransferResult(transfer_id, debit_result, credit_result)

        await uow.accounts.save(from_account)
        await uow.accounts.save(to_account)
        await uow.commit()
        return TransferResult(transfer_id, debit_result, credit_result)
