import logging
from decimal import Decimal
from uuid import uuid4

import pytest

import src.modules.account_balance.application.use_cases.credit as credit_module
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import UnsupportedCurrency
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
    patch_use_case_repos,
)

_logger = logging.getLogger("test")


@pytest.mark.asyncio
async def test_credit_increases_balance_and_writes_ledger_row(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)
    use_case = CreditAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    entry = await use_case.execute(account.id, Decimal("5.00"), "MXN", "key-1")

    assert account.balance == Decimal("15.00")
    assert entry.balance_after == Decimal("15.00")
    assert len(ledger.entries) == 1
    assert ledger.entries[0] is entry
    assert accounts.saved == [account]


@pytest.mark.asyncio
async def test_credit_locks_account_before_mutating(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)
    use_case = CreditAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    await use_case.execute(account.id, Decimal("1.00"), "MXN", "key-2")

    assert accounts.lock_order == [account.id]


@pytest.mark.asyncio
async def test_credit_commits_the_unit_of_work_on_success(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)
    uow = FakeUnitOfWork()
    use_case = CreditAccountUseCase(
        uow=uow, logger=_logger, exchange_rates=StaticExchangeRates()
    )

    await use_case.execute(account.id, Decimal("1.00"), "MXN", "key-3")

    assert uow.committed is True
    assert uow.rolled_back is False


@pytest.mark.asyncio
async def test_credit_in_a_foreign_currency_converts_before_applying(monkeypatch):
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)
    use_case = CreditAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    entry = await use_case.execute(account.id, Decimal("10.00"), "USD", "key-4")

    # 10 USD * 16.96 MXN/USD = 169.60 MXN.
    assert account.balance == Decimal("169.6000")
    assert entry.balance_after == Decimal("169.6000")
    assert entry.amount.currency == "MXN"
    assert entry.original_amount == Decimal("10.00")
    assert entry.original_currency == "USD"
    assert entry.fx_rate == Decimal("16.96")


@pytest.mark.asyncio
async def test_credit_with_unsupported_currency_is_rejected_before_any_db_work(
    monkeypatch,
):
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)
    use_case = CreditAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )

    with pytest.raises(UnsupportedCurrency):
        await use_case.execute(account.id, Decimal("10.00"), "EUR", "key-5")

    assert accounts.lock_order == []
    assert account.balance == Decimal("10.00")
    assert ledger.entries == []
