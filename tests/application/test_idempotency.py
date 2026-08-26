"""RED -> GREEN: idempotent replay.

Spec: idempotency / Duplicate request returns original result - no new
ledger entry is created and the original result is returned.
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
async def test_duplicate_idempotency_key_returns_original_result_no_reapply():
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledgers = FakeLedgerRepository()

    use_case_1 = CreditAccountUseCase(FakeUnitOfWork(), accounts, ledgers)
    first = await use_case_1.execute(account.id, Money(Decimal("5.00")), "same-key")
    assert account.balance == Decimal("15.00")

    uow2 = FakeUnitOfWork()
    use_case_2 = CreditAccountUseCase(uow2, accounts, ledgers)
    second = await use_case_2.execute(account.id, Money(Decimal("5.00")), "same-key")

    # Same result returned, balance NOT mutated a second time.
    assert second is first
    assert account.balance == Decimal("15.00")
    assert len(ledgers.entries) == 1
    assert uow2.committed is False
    assert uow2.rolled_back is True
