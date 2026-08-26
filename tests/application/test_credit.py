"""RED -> GREEN: credit use case.

Spec: balance-mutation-api / Successful credit - balance increases by
the amount and a ledger entry is created.

Instantiates CreditAccountUseCase directly with fake repos passed to
the constructor - this is the whole point of the DI refactor: no
container needed for a pure unit test.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.money import Money
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.mark.asyncio
async def test_credit_increases_balance_and_writes_ledger_row():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()
    use_case = CreditAccountUseCase(FakeUnitOfWork(), accounts, ledgers)

    entry = await use_case.execute(account.id, Money(Decimal("5.00")), "key-1")

    assert account.balance == Decimal("15.00")
    assert entry.balance_after == Decimal("15.00")
    assert len(ledgers.entries) == 1
    assert ledgers.entries[0] is entry
    assert accounts.saved == [account]


@pytest.mark.asyncio
async def test_credit_locks_account_before_mutating():
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()
    use_case = CreditAccountUseCase(FakeUnitOfWork(), accounts, ledgers)

    await use_case.execute(account.id, Money(Decimal("1.00")), "key-2")

    assert accounts.lock_order == [account.id]


@pytest.mark.asyncio
async def test_credit_commits_the_unit_of_work_on_success():
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()
    uow = FakeUnitOfWork()
    use_case = CreditAccountUseCase(uow, accounts, ledgers)

    await use_case.execute(account.id, Money(Decimal("1.00")), "key-3")

    assert uow.committed is True
    assert uow.rolled_back is False
