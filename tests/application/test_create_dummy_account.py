"""RED -> GREEN: CreateDummyAccountUseCase.

Dev/test convenience only - see the use case's docstring. Not a spec
scenario (spec.md has no "account creation" domain — this is tooling,
not a business capability), so there's no spec reference here, just
behavioral coverage: inserts a fresh row with the given/defaulted
initial_balance (every account is MXN by construction, no currency
param at all - Currency Conversion, design.md), and rejects a negative
initial_balance via the same InvalidAmount domain error credit/debit
already use.
"""

from decimal import Decimal

import pytest

from src.modules.account_balance.application.use_cases.create_dummy_account import (
    CreateDummyAccountUseCase,
)
from src.modules.account_balance.domain.errors import InvalidAmount
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.mark.asyncio
async def test_creates_account_with_mxn_currency_and_zero_balance_by_default():
    accounts = FakeAccountRepository({})
    use_case = CreateDummyAccountUseCase(FakeUnitOfWork(accounts, FakeLedgerRepository()))

    account = await use_case.execute()

    assert account.balance == Decimal("0")
    assert account.currency == "MXN"
    assert accounts.created == [account]
    assert account.id in accounts._accounts  # noqa: SLF001 - test-only peek


@pytest.mark.asyncio
async def test_creates_account_with_given_initial_balance():
    accounts = FakeAccountRepository({})
    use_case = CreateDummyAccountUseCase(FakeUnitOfWork(accounts, FakeLedgerRepository()))

    account = await use_case.execute(initial_balance=Decimal("50.00"))

    assert account.currency == "MXN"
    assert account.balance == Decimal("50.00")


@pytest.mark.asyncio
async def test_zero_initial_balance_is_allowed():
    accounts = FakeAccountRepository({})
    use_case = CreateDummyAccountUseCase(FakeUnitOfWork(accounts, FakeLedgerRepository()))

    account = await use_case.execute(initial_balance=Decimal("0"))

    assert account.balance == Decimal("0")


@pytest.mark.asyncio
async def test_negative_initial_balance_is_rejected():
    accounts = FakeAccountRepository({})
    use_case = CreateDummyAccountUseCase(FakeUnitOfWork(accounts, FakeLedgerRepository()))

    with pytest.raises(InvalidAmount):
        await use_case.execute(initial_balance=Decimal("-1.00"))

    assert accounts.created == []


@pytest.mark.asyncio
async def test_commits_the_unit_of_work_on_success():
    accounts = FakeAccountRepository({})
    uow = FakeUnitOfWork(accounts, FakeLedgerRepository())
    use_case = CreateDummyAccountUseCase(uow)

    await use_case.execute()

    assert uow.committed is True
    assert uow.rolled_back is False
