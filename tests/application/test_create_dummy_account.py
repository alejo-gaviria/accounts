import logging
from decimal import Decimal

import pytest

import src.modules.account_balance.application.use_cases.create_dummy_account as create_dummy_account_module
from src.modules.account_balance.application.use_cases.create_dummy_account import (
    CreateDummyAccountUseCase,
)
from src.modules.account_balance.domain.errors import InvalidAmount
from tests.application.fakes import (
    FakeAccountRepository,
    FakeUnitOfWork,
)

_logger = logging.getLogger("test")


def _patch_accounts(monkeypatch, accounts) -> None:
    monkeypatch.setattr(
        create_dummy_account_module,
        "SqlAccountRepository",
        lambda session, logger: accounts,
    )


@pytest.mark.asyncio
async def test_creates_account_with_mxn_currency_and_zero_balance_by_default(
    monkeypatch,
):
    accounts = FakeAccountRepository({})
    _patch_accounts(monkeypatch, accounts)
    use_case = CreateDummyAccountUseCase(uow=FakeUnitOfWork(), logger=_logger)

    account = await use_case.execute()

    assert account.balance == Decimal("0")
    assert account.currency == "MXN"
    assert accounts.created == [account]
    assert account.id in accounts._accounts  # noqa: SLF001 - test-only peek


@pytest.mark.asyncio
async def test_creates_account_with_given_initial_balance(monkeypatch):
    accounts = FakeAccountRepository({})
    _patch_accounts(monkeypatch, accounts)
    use_case = CreateDummyAccountUseCase(uow=FakeUnitOfWork(), logger=_logger)

    account = await use_case.execute(initial_balance=Decimal("50.00"))

    assert account.currency == "MXN"
    assert account.balance == Decimal("50.00")


@pytest.mark.asyncio
async def test_zero_initial_balance_is_allowed(monkeypatch):
    accounts = FakeAccountRepository({})
    _patch_accounts(monkeypatch, accounts)
    use_case = CreateDummyAccountUseCase(uow=FakeUnitOfWork(), logger=_logger)

    account = await use_case.execute(initial_balance=Decimal("0"))

    assert account.balance == Decimal("0")


@pytest.mark.asyncio
async def test_negative_initial_balance_is_rejected(monkeypatch):
    accounts = FakeAccountRepository({})
    _patch_accounts(monkeypatch, accounts)
    use_case = CreateDummyAccountUseCase(uow=FakeUnitOfWork(), logger=_logger)

    with pytest.raises(InvalidAmount):
        await use_case.execute(initial_balance=Decimal("-1.00"))

    assert accounts.created == []


@pytest.mark.asyncio
async def test_commits_the_unit_of_work_on_success(monkeypatch):
    accounts = FakeAccountRepository({})
    _patch_accounts(monkeypatch, accounts)
    uow = FakeUnitOfWork()
    use_case = CreateDummyAccountUseCase(uow=uow, logger=_logger)

    await use_case.execute()

    assert uow.committed is True
    assert uow.rolled_back is False
