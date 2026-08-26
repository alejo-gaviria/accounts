"""Idempotent replay tests: a duplicate request returns the original
result — no new ledger entry is created. A replay detects the existing
entry before mutating anything and returns normally, so the UnitOfWork
commits (an empty, no-op transaction) rather than rolling back — a
replay is a successful outcome, not an error.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_original_result_no_reapply():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()

    use_case_1 = CreditAccountUseCase(
        FakeUnitOfWork(accounts, ledger), StaticExchangeRates()
    )
    first = await use_case_1.execute(account.id, Decimal("5.00"), "MXN", "same-key")
    assert account.balance == Decimal("15.00")

    uow2 = FakeUnitOfWork(accounts, ledger)
    use_case_2 = CreditAccountUseCase(uow2, StaticExchangeRates())
    second = await use_case_2.execute(account.id, Decimal("5.00"), "MXN", "same-key")

    assert second is first
    assert account.balance == Decimal("15.00")
    assert len(ledger.entries) == 1
    assert uow2.committed is True
    assert uow2.rolled_back is False
