"""RED -> GREEN: debit use case.

Spec: balance-mutation-api / Insufficient funds on debit/transfer -
rejected with no state change (no ledger entry created, no balance
change, transaction rolled back).
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.use_cases.debit import (
    DebitAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import InsufficientFunds
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.mark.asyncio
async def test_debit_decreases_balance_when_sufficient_funds():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledger)
    use_case = DebitAccountUseCase(uow, StaticExchangeRates())

    entry = await use_case.execute(account.id, Decimal("4.00"), "MXN", "key-1")

    assert account.balance == Decimal("6.00")
    assert entry.balance_after == Decimal("6.00")
    assert uow.committed is True


@pytest.mark.asyncio
async def test_debit_raises_insufficient_funds_and_writes_no_ledger_row():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    uow = FakeUnitOfWork(accounts, ledger)
    use_case = DebitAccountUseCase(uow, StaticExchangeRates())

    with pytest.raises(InsufficientFunds):
        await use_case.execute(account.id, Decimal("10.01"), "MXN", "key-2")

    assert ledger.entries == []
    assert account.balance == Decimal("10.00")
    assert accounts.saved == []
    assert uow.committed is False
    assert uow.rolled_back is True


@pytest.mark.asyncio
async def test_debit_in_a_foreign_currency_converts_before_checking_funds():
    # 100 MXN balance; debit 10 USD == 169.60 MXN -> insufficient,
    # even though "10" alone would have been fine.
    account = Account(id=uuid4(), balance=Decimal("100.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    use_case = DebitAccountUseCase(
        FakeUnitOfWork(accounts, ledger), StaticExchangeRates()
    )

    with pytest.raises(InsufficientFunds):
        await use_case.execute(account.id, Decimal("10.00"), "USD", "key-3")

    assert account.balance == Decimal("100.00")
    assert ledger.entries == []


@pytest.mark.asyncio
async def test_debit_in_a_foreign_currency_records_original_amount_and_rate():
    account = Account(id=uuid4(), balance=Decimal("200.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    use_case = DebitAccountUseCase(
        FakeUnitOfWork(accounts, ledger), StaticExchangeRates()
    )

    entry = await use_case.execute(account.id, Decimal("10.00"), "USD", "key-4")

    assert account.balance == Decimal("30.4000")  # 200 - 169.60
    assert entry.original_amount == Decimal("10.00")
    assert entry.original_currency == "USD"
    assert entry.fx_rate == Decimal("16.96")
