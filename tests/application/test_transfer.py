"""RED -> GREEN: transfer use case.

Spec: balance-mutation-api / Successful transfer - source debits and
destination credits atomically with two linked ledger entries.
Design: both account locks acquired in ascending-id order so opposite-
direction concurrent transfers can't deadlock.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.use_cases.transfer import transfer
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import InsufficientFunds
from src.modules.account_balance.domain.money import Money
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


def _two_accounts() -> tuple[Account, Account]:
    ids = sorted([uuid4(), uuid4()])
    low = Account(id=ids[0], balance=Decimal("20.00"))
    high = Account(id=ids[1], balance=Decimal("5.00"))
    return low, high


@pytest.mark.asyncio
async def test_transfer_moves_funds_and_links_both_ledger_entries():
    low, high = _two_accounts()  # low.id < high.id
    accounts = FakeAccountRepository({low.id: low, high.id: high})
    ledgers = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledgers)

    result = await transfer(
        uow, low.id, high.id, Money(Decimal("5.00")), "req-1"
    )

    assert low.balance == Decimal("15.00")
    assert high.balance == Decimal("10.00")
    assert result.debit_entry.transfer_id == result.transfer_id
    assert result.credit_entry.transfer_id == result.transfer_id
    assert {e.account_id for e in ledgers.entries} == {low.id, high.id}
    assert uow.committed is True


@pytest.mark.asyncio
async def test_transfer_locks_accounts_in_ascending_id_order_regardless_of_direction():
    low, high = _two_accounts()

    accounts_a = FakeAccountRepository({low.id: low, high.id: high})
    uow_a = FakeUnitOfWork(accounts_a, FakeLedgerRepository())
    await transfer(uow_a, low.id, high.id, Money(Decimal("1.00")), "req-a")
    assert accounts_a.lock_order == [low.id, high.id]

    low2, high2 = _two_accounts()
    accounts_b = FakeAccountRepository({low2.id: low2, high2.id: high2})
    uow_b = FakeUnitOfWork(accounts_b, FakeLedgerRepository())
    # Opposite direction: destination has the lower id this time.
    await transfer(uow_b, high2.id, low2.id, Money(Decimal("1.00")), "req-b")
    assert accounts_b.lock_order == [low2.id, high2.id]


@pytest.mark.asyncio
async def test_transfer_insufficient_funds_rolls_back_with_no_ledger_rows():
    low, high = _two_accounts()
    accounts = FakeAccountRepository({low.id: low, high.id: high})
    ledgers = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledgers)

    with pytest.raises(InsufficientFunds):
        await transfer(uow, high.id, low.id, Money(Decimal("999.00")), "req-2")

    assert ledgers.entries == []
    assert uow.committed is False
    assert uow.rolled_back is True
