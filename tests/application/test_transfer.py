"""RED -> GREEN: transfer use case.

Spec: balance-mutation-api / Successful transfer - source debits and
destination credits atomically with two linked ledger entries.
Design: both account locks acquired in ascending-id order so opposite-
direction concurrent transfers can't deadlock. Currency Conversion:
converted once, using the request currency - both legs apply the same
converted MXN amount (no per-leg re-conversion, no "accounts differ"
case since every account is MXN).
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.use_cases.transfer import TransferUseCase
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import InsufficientFunds
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
    ledger = FakeLedgerRepository()
    use_case = TransferUseCase(
        FakeUnitOfWork(accounts, ledger), StaticExchangeRates()
    )

    result = await use_case.execute(low.id, high.id, Decimal("5.00"), "MXN", "req-1")

    assert low.balance == Decimal("15.00")
    assert high.balance == Decimal("10.00")
    assert result.debit_entry.transfer_id == result.transfer_id
    assert result.credit_entry.transfer_id == result.transfer_id
    assert {e.account_id for e in ledger.entries} == {low.id, high.id}


@pytest.mark.asyncio
async def test_transfer_commits_the_unit_of_work_on_success():
    low, high = _two_accounts()
    accounts = FakeAccountRepository({low.id: low, high.id: high})
    ledger = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledger)
    use_case = TransferUseCase(uow, StaticExchangeRates())

    await use_case.execute(low.id, high.id, Decimal("5.00"), "MXN", "req-1")

    assert uow.committed is True


@pytest.mark.asyncio
async def test_transfer_locks_accounts_in_ascending_id_order_regardless_of_direction():
    low, high = _two_accounts()

    accounts_a = FakeAccountRepository({low.id: low, high.id: high})
    use_case_a = TransferUseCase(
        FakeUnitOfWork(accounts_a, FakeLedgerRepository()), StaticExchangeRates()
    )
    await use_case_a.execute(low.id, high.id, Decimal("1.00"), "MXN", "req-a")
    assert accounts_a.lock_order == [low.id, high.id]

    low2, high2 = _two_accounts()
    accounts_b = FakeAccountRepository({low2.id: low2, high2.id: high2})
    use_case_b = TransferUseCase(
        FakeUnitOfWork(accounts_b, FakeLedgerRepository()), StaticExchangeRates()
    )
    # Opposite direction: destination has the lower id this time.
    await use_case_b.execute(high2.id, low2.id, Decimal("1.00"), "MXN", "req-b")
    assert accounts_b.lock_order == [low2.id, high2.id]


@pytest.mark.asyncio
async def test_transfer_insufficient_funds_rolls_back_with_no_ledger_rows():
    low, high = _two_accounts()
    accounts = FakeAccountRepository({low.id: low, high.id: high})
    ledger = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledger)
    use_case = TransferUseCase(uow, StaticExchangeRates())

    with pytest.raises(InsufficientFunds):
        await use_case.execute(
            high.id, low.id, Decimal("999.00"), "MXN", "req-2"
        )

    assert ledger.entries == []
    assert uow.committed is False
    assert uow.rolled_back is True


@pytest.mark.asyncio
async def test_transfer_in_a_foreign_currency_converts_once_for_both_legs():
    low, high = _two_accounts()  # low balance=20, high balance=5
    accounts = FakeAccountRepository({low.id: low, high.id: high})
    ledger = FakeLedgerRepository()
    use_case = TransferUseCase(
        FakeUnitOfWork(accounts, ledger), StaticExchangeRates()
    )

    # 1 USD -> 16.96 MXN.
    result = await use_case.execute(low.id, high.id, Decimal("1.00"), "USD", "req-3")

    assert low.balance == Decimal("3.0400")  # 20 - 16.96
    assert high.balance == Decimal("21.9600")  # 5 + 16.96
    for entry in (result.debit_entry, result.credit_entry):
        assert entry.original_amount == Decimal("1.00")
        assert entry.original_currency == "USD"
        assert entry.fx_rate == Decimal("16.96")
        assert entry.amount.amount == Decimal("16.9600")
        assert entry.amount.currency == "MXN"
