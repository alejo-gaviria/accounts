import logging
from decimal import Decimal
from uuid import uuid4

import pytest

import src.modules.account_balance.application.use_cases.debit as debit_module
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
    patch_use_case_repos,
)

_logger = logging.getLogger("test")


@pytest.mark.asyncio
async def test_debit_decreases_balance_when_sufficient_funds(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, debit_module, accounts, ledger)
    uow = FakeUnitOfWork()
    use_case = DebitAccountUseCase(
        uow=uow, logger=_logger, exchange_rates=StaticExchangeRates()
    )

    entry = await use_case.execute(account.id, Decimal("4.00"), "MXN", "key-1")

    assert account.balance == Decimal("6.00")
    assert entry.balance_after == Decimal("6.00")
    assert uow.committed is True


@pytest.mark.asyncio
async def test_debit_raises_insufficient_funds_and_writes_no_ledger_row(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, debit_module, accounts, ledger)
    uow = FakeUnitOfWork()
    use_case = DebitAccountUseCase(
        uow=uow, logger=_logger, exchange_rates=StaticExchangeRates()
    )

    with pytest.raises(InsufficientFunds):
        await use_case.execute(account.id, Decimal("10.01"), "MXN", "key-2")

    assert ledger.entries == []
    assert account.balance == Decimal("10.00")
    assert accounts.saved == []
    assert uow.committed is False
    assert uow.rolled_back is True


@pytest.mark.asyncio
async def test_debit_in_a_foreign_currency_converts_before_checking_funds(
    monkeypatch,
):
    # 100 MXN balance; debit 10 USD == 169.60 MXN -> insufficient.
    account = Account(id=uuid4(), balance=Decimal("100.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, debit_module, accounts, ledger)
    use_case = DebitAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    with pytest.raises(InsufficientFunds):
        await use_case.execute(account.id, Decimal("10.00"), "USD", "key-3")

    assert account.balance == Decimal("100.00")
    assert ledger.entries == []


@pytest.mark.asyncio
async def test_debit_in_a_foreign_currency_records_original_amount_and_rate(
    monkeypatch,
):
    account = Account(id=uuid4(), balance=Decimal("200.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, debit_module, accounts, ledger)
    use_case = DebitAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    entry = await use_case.execute(account.id, Decimal("10.00"), "USD", "key-4")

    assert account.balance == Decimal("30.4000")  # 200 - 169.60
    assert entry.original_amount == Decimal("10.00")
    assert entry.original_currency == "USD"
    assert entry.fx_rate == Decimal("16.96")
