"""RED -> GREEN: debit use case.

Spec: balance-mutation-api / Insufficient funds on debit/transfer -
rejected with no state change (no ledger entry created, no balance
change, transaction rolled back).
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.use_cases.debit import (
    DebitAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import InsufficientFunds
from src.modules.account_balance.domain.money import Money
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.mark.asyncio
async def test_debit_decreases_balance_when_sufficient_funds():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()
    uow = FakeUnitOfWork()
    use_case = DebitAccountUseCase(uow, accounts, ledgers)

    entry = await use_case.execute(account.id, Money(Decimal("4.00")), "key-1")

    assert account.balance == Decimal("6.00")
    assert entry.balance_after == Decimal("6.00")
    assert uow.committed is True


@pytest.mark.asyncio
async def test_debit_raises_insufficient_funds_and_writes_no_ledger_row():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()
    uow = FakeUnitOfWork()
    use_case = DebitAccountUseCase(uow, accounts, ledgers)

    with pytest.raises(InsufficientFunds):
        await use_case.execute(account.id, Money(Decimal("10.01")), "key-2")

    assert ledgers.entries == []
    assert account.balance == Decimal("10.00")
    assert accounts.saved == []
    assert uow.committed is False
    assert uow.rolled_back is True
